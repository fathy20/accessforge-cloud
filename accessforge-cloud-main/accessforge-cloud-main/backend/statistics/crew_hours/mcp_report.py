"""Read-only LEON MCP Report Wizard integration."""

import json
import re
from typing import Any, Mapping

import httpx

from .config import LeonConfiguration
from .errors import LeonAuthenticationError, LeonConfigurationError, LeonContractError, LeonResponseError, LeonTimeoutError, LeonTransportError
from .token_provider import LeonAccessTokenProvider
from .transport import BearerAccessTokenHeaderBuilder, LeonHttpTransport, LeonRawResponse, LeonRequest


MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_REPORT_TOOL = "get-report-wizard-flight-scope-report"

MCP_REPORT_COLUMNS = (
    "crew_codes",
    "crew_names",
    "blockTimeJourneyLog",
    "blockTimePlan",
)


def fetch_official_totals(
    configuration: LeonConfiguration,
    transport: LeonHttpTransport,
    token_provider: LeonAccessTokenProvider,
    from_date: str,
    to_date: str,
) -> dict[str, str]:
    """Fetch and aggregate the official LEON Report Wizard block times."""
    mcp_url = _mcp_url(configuration)
    date_filter = {
        "start": f"{_validate_date(from_date)}T00:00:00Z",
        "end": f"{_validate_date(to_date)}T23:59:59Z",
    }
    if date_filter["start"][:10] > date_filter["end"][:10]:
        raise LeonContractError("MCP report start date must not be after end date.")

    arguments = {
        "dateFilter": date_filter,
        "columnList": list(MCP_REPORT_COLUMNS),
    }

    for attempt in range(2):
        access_token = token_provider.get_access_token()
        initialized = _send_json_rpc(
            configuration,
            transport,
            mcp_url,
            access_token,
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "redsea-crew-hours", "version": "1.0"},
            }},
        )
        if initialized.status_code in {401, 403}:
            token_provider.invalidate()
            if attempt == 0:
                continue
            raise LeonAuthenticationError("LEON MCP authentication failed.")
        session_id = _session_id(initialized.headers)
        _ensure_rpc_success(initialized)

        response = _send_json_rpc(
            configuration,
            transport,
            mcp_url,
            access_token,
            {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
                "name": MCP_REPORT_TOOL,
                "arguments": arguments,
            }},
            session_id=session_id,
        )
        if response.status_code in {401, 403}:
            token_provider.invalidate()
            if attempt == 0:
                continue
            raise LeonAuthenticationError("LEON MCP authentication failed.")
        return _aggregate_report_rows(_extract_report_rows(_ensure_rpc_success(response)))

    raise AssertionError("MCP authentication retry loop exhausted unexpectedly.")


def _send_json_rpc(
    configuration: LeonConfiguration,
    transport: LeonHttpTransport,
    mcp_url: str,
    access_token: str,
    payload: Mapping[str, Any],
    *,
    session_id: str | None = None,
) -> LeonRawResponse:
    headers = {
        "Content-Type": "application/json",
        "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
        **BearerAccessTokenHeaderBuilder().build(access_token),
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    request = LeonRequest(
        method="POST",
        url=mcp_url,
        headers=headers,
        json_body=payload,
    )
    try:
        return transport.send(request, configuration.timeout_seconds)
    except httpx.TimeoutException as exc:
        raise LeonTimeoutError("LEON MCP request timed out.") from exc
    except httpx.HTTPError as exc:
        raise LeonTransportError("LEON MCP transport failed.") from exc


def _ensure_rpc_success(response: LeonRawResponse) -> Mapping[str, Any]:
    if response.status_code < 200 or response.status_code >= 300:
        raise LeonResponseError(f"LEON MCP returned HTTP {response.status_code}.")
    payload = _parse_rpc_body(response.body)
    if payload.get("error"):
        raise LeonResponseError("LEON MCP returned an RPC error.")
    result = payload.get("result")
    if not isinstance(result, dict):
        raise LeonResponseError("LEON MCP response did not contain a result object.")
    if result.get("isError") is True:
        raise LeonResponseError("LEON MCP report tool returned an error.")
    return result


def _parse_rpc_body(body: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        payload = None
        for line in body.splitlines():
            if line.startswith("data:"):
                try:
                    payload = json.loads(line[5:].strip())
                except (TypeError, ValueError):
                    continue
                if isinstance(payload, dict):
                    break
        if payload is None:
            raise LeonResponseError("LEON MCP response was not valid JSON.")
    if not isinstance(payload, dict):
        raise LeonResponseError("LEON MCP response had an invalid shape.")
    return payload


def _extract_report_rows(result: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    candidates: list[Any] = []
    if result.get("structuredContent") is not None:
        candidates.append(result["structuredContent"])
    candidates.append(result.get("content"))
    for candidate in candidates:
        rows = _find_rows(candidate)
        if rows is not None:
            return rows
    raise LeonResponseError("LEON MCP report response did not contain report rows.")


def _find_rows(value: Any) -> list[Mapping[str, Any]] | None:
    if isinstance(value, Mapping):
        if "crew_codes" in value:
            return [value]
        for key in ("data", "rows", "items", "records", "report", "flightScopeReport"):
            if key in value:
                rows = _find_rows(value[key])
                if rows is not None:
                    return rows
        for nested in value.values():
            rows = _find_rows(nested)
            if rows is not None:
                return rows
        return None
    if isinstance(value, list):
        if value and all(isinstance(item, Mapping) and "crew_codes" in item for item in value):
            return value
        for item in value:
            if isinstance(item, Mapping) and item.get("type") == "text":
                text = item.get("text")
                if isinstance(text, str):
                    try:
                        rows = _find_rows(json.loads(text))
                    except (TypeError, ValueError):
                        rows = None
                    if rows is not None:
                        return rows
            rows = _find_rows(item)
            if rows is not None:
                return rows
    return None


def _aggregate_report_rows(rows: list[Mapping[str, Any]]) -> dict[str, str]:
    totals: dict[str, int] = {}
    for row in rows:
        codes = row.get("crew_codes")
        if not isinstance(codes, list) or any(not isinstance(code, str) for code in codes):
            raise LeonContractError("LEON MCP report row had invalid crew_codes.")
        block_time = row.get("blockTimeJourneyLog")
        if block_time in (None, ""):
            continue
        minutes = _parse_block_time(block_time)
        for code in codes:
            normalized_code = code.strip()
            if normalized_code:
                totals[normalized_code] = totals.get(normalized_code, 0) + minutes
    return {code: _format_minutes(minutes) for code, minutes in totals.items()}


def _parse_block_time(value: Any) -> int:
    if not isinstance(value, str):
        raise LeonContractError("LEON MCP report blockTimeJourneyLog was invalid.")
    match = re.fullmatch(r"(\d{1,3}):(\d{2})", value.strip())
    if not match or int(match.group(2)) > 59:
        raise LeonContractError("LEON MCP report blockTimeJourneyLog was invalid.")
    return int(match.group(1)) * 60 + int(match.group(2))


def _format_minutes(minutes: int) -> str:
    return f"{minutes // 60}:{minutes % 60:02d}"


def _validate_date(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise LeonContractError("MCP report dates must use strict YYYY-MM-DD values.")
    from datetime import date
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise LeonContractError("MCP report dates must be valid calendar dates.") from exc
    return value


def _mcp_url(configuration: LeonConfiguration) -> str:
    if not configuration.mcp_url:
        raise LeonConfigurationError("LEON_MCP_URL is required for official MCP report totals.")
    return configuration.mcp_url.rstrip("/")


def _session_id(headers: Mapping[str, str]) -> str | None:
    for name, value in headers.items():
        if name.lower() == "mcp-session-id":
            return value
    return None
