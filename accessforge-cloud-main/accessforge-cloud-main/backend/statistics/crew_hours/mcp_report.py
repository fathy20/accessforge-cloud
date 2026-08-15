"""Read-only LEON MCP Report Wizard integration."""

import json
import re
from typing import Any, Mapping

import httpx

from .config import LeonConfiguration
from .domain import buffered_query_dates, normalize_report_row, select_rows_for_period
from .errors import LeonAuthenticationError, LeonConfigurationError, LeonContractError, LeonResponseError, LeonTimeoutError, LeonTransportError
from .token_provider import LeonAccessTokenProvider
from .transport import BearerAccessTokenHeaderBuilder, LeonHttpTransport, LeonRawResponse, LeonRequest


MCP_PROTOCOL_VERSION = "2025-03-26"
MCP_REPORT_TOOL = "get-report-wizard-flight-scope-report"

REQUIRED_COLUMNS = (
    "scope_row_unique_id",
    "crew_codes",
    "blockTimeJourneyLog",
)
OPTIONAL_COLUMNS = (
    "unique_id",
    "crew_names",
    "crew_position_names",
    "date_STD_log_UTC",
    "registration",
    "acftType",
    "flightNo",
    "jl_adep_preferred_code",
    "jl_ades_preferred_code",
    "JL_STD_UTC",
    "JL_STA_UTC",
    "positioning_crew",
)
MCP_REPORT_COLUMNS = REQUIRED_COLUMNS + OPTIONAL_COLUMNS


class OfficialMcpReport(dict[str, str]):
    """Official totals plus the validated rows used to build the report.

    The mapping interface preserves the existing ``fetch_official_totals``
    contract while the row payload lets the service render the authoritative
    MCP report without a second flight source.
    """

    def __init__(
        self,
        totals: Mapping[str, str],
        rows: list[Mapping[str, Any]],
        total_minutes: Mapping[str, int] | None = None,
        records_count: int | None = None,
    ):
        super().__init__(totals)
        self.total_minutes: Mapping[str, int] = dict(
            total_minutes
            if total_minutes is not None
            else _derive_total_minutes(totals)
        )
        self.rows = tuple(dict(row) for row in rows)
        self.records_count = len(self.rows) if records_count is None else records_count

def fetch_official_totals(
    configuration: LeonConfiguration,
    transport: LeonHttpTransport,
    token_provider: LeonAccessTokenProvider,
    from_date: str,
    to_date: str,
) -> OfficialMcpReport:
    """Fetch the official report while preserving the legacy totals mapping."""
    return fetch_official_report(configuration, transport, token_provider, from_date, to_date)

def fetch_official_report(
    configuration: LeonConfiguration,
    transport: LeonHttpTransport,
    token_provider: LeonAccessTokenProvider,
    from_date: str,
    to_date: str,
) -> OfficialMcpReport:
    """Fetch and validate the official LEON Report Wizard rows and totals."""
    mcp_url = _mcp_url(configuration)
    validated_from = _validate_date(from_date)
    validated_to = _validate_date(to_date)
    if validated_from > validated_to:
        raise LeonContractError("MCP report start date must not be after end date.")
    buffered_from, buffered_to = buffered_query_dates(validated_from, validated_to)
    date_filter = {
        "start": f"{buffered_from}T00:00:00Z",
        "end": f"{buffered_to}T23:59:59Z",
    }

    arguments = {
        "dateFilter": date_filter,
        "columnList": list(MCP_REPORT_COLUMNS),
        "acftNidList": None,
        "crewMemberNidList": None,
        "adepLocationNidList": None,
        "adesLocationNidList": None,
        "airportLocationNidList": None,
        "isCanceled": None,
        "permitsCountryList": None,
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
        fetched_rows = _extract_report_rows(_ensure_rpc_success(response))
        _validate_required_rows(fetched_rows)
        rows = select_rows_for_period(fetched_rows, validated_from, validated_to)
        formatted_totals, total_minutes = _aggregate_report_rows(rows)
        return OfficialMcpReport(
            formatted_totals,
            rows,
            total_minutes,
            records_count=len(fetched_rows),
        )

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
        "Accept": "application/json, text/event-stream",
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
        payloads: list[Mapping[str, Any]] = []
        for line in body.splitlines():
            if not line.startswith("data:"):
                continue
            raw_event = line[5:].strip()
            if not raw_event or raw_event == "[DONE]":
                continue
            try:
                event_payload = json.loads(raw_event)
            except (TypeError, ValueError):
                continue
            if isinstance(event_payload, dict):
                payloads.append(event_payload)
        if not payloads:
            raise LeonResponseError("LEON MCP response was not valid JSON.")
        payload = next(
            (event for event in reversed(payloads) if "result" in event or "error" in event),
            payloads[-1],
        )
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


def _find_rows(value: Any, *, decode_text: bool = True) -> list[Mapping[str, Any]] | None:
    if isinstance(value, str):
        if not decode_text:
            return None
        decoded = _decode_embedded_json(value)
        if decoded is not None:
            return _find_rows(decoded, decode_text=False)
        return None
    if isinstance(value, Mapping):
        # Anchor on crew_codes, not REQUIRED_COLUMNS, so missing required columns reach named validation.
        if "crew_codes" in value:
            return [value]
        if isinstance(value.get("text"), str) and decode_text:
            decoded = _decode_embedded_json(value["text"])
            if decoded is not None:
                rows = _find_rows(decoded, decode_text=False)
                if rows is not None:
                    return rows
        for key in ("data", "rows", "items", "records", "report", "flightScopeReport", "resource"):
            if key in value:
                rows = _find_rows(value[key], decode_text=decode_text)
                if rows is not None:
                    return rows
        for key, nested in value.items():
            if key in {"text", "resource"}:
                continue
            rows = _find_rows(nested, decode_text=decode_text)
            if rows is not None:
                return rows
        return None
    if isinstance(value, list):
        if value and all(isinstance(item, Mapping) for item in value) and any("crew_codes" in item for item in value):
            return value
        for item in value:
            rows = _find_rows(item, decode_text=decode_text)
            if rows is not None:
                return rows
    return None


def _decode_embedded_json(value: str) -> Any | None:
    """Decode one JSON layer and one optional nested JSON string layer."""
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        return None
    if isinstance(decoded, str):
        try:
            return json.loads(decoded)
        except (TypeError, ValueError):
            return decoded
    return decoded


def _aggregate_report_rows(
    rows: list[Mapping[str, Any]],
) -> tuple[dict[str, str], dict[str, int]]:
    _validate_required_rows(rows)
    totals: dict[str, int] = {}
    for row in rows:
        codes = row.get("crew_codes")
        if not isinstance(codes, list) or any(not isinstance(code, str) for code in codes):
            raise LeonContractError("LEON MCP report row had invalid crew_codes.")
        normalized_row = normalize_report_row(row)
        block_time = row.get("blockTimeJourneyLog")
        if block_time in (None, ""):
            continue
        minutes = _parse_block_time(block_time)
        for crew_slot in normalized_row.crew:
            if not crew_slot.is_operating:
                continue
            totals[crew_slot.code] = totals.get(crew_slot.code, 0) + minutes
    return (
        {code: _format_minutes(minutes) for code, minutes in totals.items()},
        totals,
    )


def _validate_required_rows(rows: list[Mapping[str, Any]]) -> None:
    for row in rows:
        if not isinstance(row, Mapping):
            raise LeonContractError("LEON MCP report row had an invalid shape.")
        for column in REQUIRED_COLUMNS:
            if column not in row:
                raise LeonContractError(
                    f"LEON MCP report row was missing required column '{column}'."
                )


def _derive_total_minutes(totals: Mapping[str, str]) -> dict[str, int]:
    """Recover raw minutes for legacy two-argument report construction."""
    derived: dict[str, int] = {}
    for code, formatted in totals.items():
        if not isinstance(formatted, str):
            continue
        match = re.fullmatch(r"(\d+):(\d{2})", formatted)
        if match and int(match.group(2)) <= 59:
            derived[code] = int(match.group(1)) * 60 + int(match.group(2))
    return derived


def _parse_block_time(value: Any) -> int:
    if not isinstance(value, str):
        raise LeonContractError("LEON MCP report blockTimeJourneyLog was invalid.")
    match = re.fullmatch(r"(\d+):(\d{2})(?::(\d{2}))?", value.strip())
    if not match or int(match.group(2)) > 59 or (match.group(3) is not None and int(match.group(3)) > 59):
        raise LeonContractError("LEON MCP report blockTimeJourneyLog was invalid.")
    if match.group(3) is not None and int(match.group(3)) != 0:
        raise LeonContractError(
            "LEON MCP report blockTimeJourneyLog carried unsupported non-zero seconds."
        )
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
