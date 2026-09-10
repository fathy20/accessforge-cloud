"""One-row identifier probe across the three LEON crew-hours sources.

The report pipeline joins Report Wizard rows (``unique_id``) to the FTL duty
index (keyed by ``trNid``) and the flight-list index (keyed by ``flightNid``)
on the ASSUMPTION that all three are the same number. The column metadata ADR
(docs/architecture/leon-report-wizard-columns.md) marks the report identifiers
AMBIGUOUS, and the assumption has never been verified live. This probe fetches
the same day from all three endpoints and prints every candidate identifier
side by side so an operator can confirm — or refute — the join key once,
against real data.

Usage (reads LEON_* from the environment / .env, exactly like the app):

    python -m backend.statistics.crew_hours.tools.id_probe --date 2026-06-02
    python -m backend.statistics.crew_hours.tools.id_probe --date 2026-06-02 --flight RSX331

It prints identifiers, times, airports, and crew codes only — never tokens,
raw envelopes, or credentials. It performs read-only calls.

This tool deliberately does NOT remap anything in code: if the IDs disagree,
the fix is a reviewed change to the join key, not a silent guess here.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, Mapping, Sequence

# Loading backend.config is what reads the .env files (root and backend/.env)
# exactly as the application does; without it LEON_* is never populated and
# the probe cannot run at all. Import side effect is intentional.
import backend.config  # noqa: F401

from ..augmented import _extract_duty_rows, build_duty_list_query
from ..config import load_leon_configuration
from ..flight_query import build_flight_list_query
from ..graphql import LeonGraphQLExecutor
from ..mcp_report import (
    MCP_PROTOCOL_VERSION,
    MCP_REPORT_TOOL,
    _ensure_rpc_success,
    _extract_report_rows,
    _mcp_url,
    _send_json_rpc,
    _session_id,
)
from ..token_provider import LeonAccessTokenProvider
from ..transport import BearerAccessTokenHeaderBuilder, HttpxLeonTransport


# Every plausible row/leg identifier the Report Wizard exposes, probed at once.
PROBE_REPORT_COLUMNS = (
    "scope_row_unique_id",
    "unique_id",
    "unique_leg_number",
    "trip_nid",
    "crew_codes",
    "blockTimeJourneyLog",
    "flightNo",
    "date_STD_log_UTC",
    "JL_STD_UTC",
    "JL_STA_UTC",
)

_ABSENT = "—"


def _cell(row: Mapping[str, Any], key: str) -> str:
    value = row.get(key)
    if value is None or value == "":
        return _ABSENT
    return str(value)


def format_report_row(row: Mapping[str, Any]) -> str:
    """Render one Report Wizard row's candidate identifiers side by side."""

    return (
        f"flightNo={_cell(row, 'flightNo')} "
        f"STD={_cell(row, 'JL_STD_UTC')} "
        f"scope_row_unique_id={_cell(row, 'scope_row_unique_id')} "
        f"unique_id={_cell(row, 'unique_id')} "
        f"unique_leg_number={_cell(row, 'unique_leg_number')} "
        f"trip_nid={_cell(row, 'trip_nid')}"
    )


def format_flight_list_row(flight: Mapping[str, Any]) -> str:
    def airport(value: Any) -> str:
        if isinstance(value, Mapping):
            code = value.get("code")
            if isinstance(code, Mapping):
                return str(code.get("icao") or code.get("iata") or _ABSENT)
        return _ABSENT

    return (
        f"flightNid={_cell(flight, 'flightNid')} "
        f"start={_cell(flight, 'startTimeUTC')} "
        f"end={_cell(flight, 'endTimeUTC')} "
        f"{airport(flight.get('startAirport'))}->{airport(flight.get('endAirport'))}"
    )


def format_duty_row(duty: Mapping[str, Any]) -> str:
    crew_member = duty.get("crewMember")
    code = (
        crew_member.get("code") if isinstance(crew_member, Mapping) else None
    ) or _ABSENT
    sectors = duty.get("sectorList")
    tr_nids = (
        ", ".join(str(sector.get("trNid")) for sector in sectors if isinstance(sector, Mapping))
        if isinstance(sectors, list)
        else _ABSENT
    )
    return (
        f"crew={code} "
        f"crewAugmentation={_cell(duty, 'crewAugmentation')} "
        f"trNid=[{tr_nids or _ABSENT}]"
    )


def _fetch_probe_report_rows(configuration, transport, token_provider, day: str) -> list[Mapping[str, Any]]:
    mcp_url = _mcp_url(configuration)
    access_token = token_provider.get_access_token()
    initialized = _send_json_rpc(
        configuration,
        transport,
        mcp_url,
        access_token,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "redsea-crew-hours-id-probe", "version": "1.0"},
            },
        },
    )
    session_id = _session_id(initialized.headers)
    _ensure_rpc_success(initialized)
    response = _send_json_rpc(
        configuration,
        transport,
        mcp_url,
        access_token,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": MCP_REPORT_TOOL,
                "arguments": {
                    "dateFilter": {
                        "start": f"{day}T00:00:00Z",
                        "end": f"{day}T23:59:59Z",
                    },
                    "columnList": list(PROBE_REPORT_COLUMNS),
                    "acftNidList": None,
                    "crewMemberNidList": None,
                    "adepLocationNidList": None,
                    "adesLocationNidList": None,
                    "airportLocationNidList": None,
                    "isCanceled": None,
                    "permitsCountryList": None,
                },
            },
        },
        session_id=session_id,
    )
    return _extract_report_rows(_ensure_rpc_success(response))


def run_probe(day: str, flight_filter: str | None, *, out=sys.stdout) -> int:
    configuration = load_leon_configuration()
    transport = HttpxLeonTransport()
    token_provider = LeonAccessTokenProvider(configuration, transport)
    executor = LeonGraphQLExecutor(
        configuration,
        transport,
        token_provider,
        BearerAccessTokenHeaderBuilder(),
    )

    print(f"LEON identifier probe for {day}", file=out)
    print("=" * 72, file=out)

    print("\n[1] Report Wizard rows (MCP) — the four candidate row identifiers:", file=out)
    report_rows = _fetch_probe_report_rows(configuration, transport, token_provider, day)
    shown = 0
    for row in report_rows:
        if flight_filter and str(row.get("flightNo") or "").strip().upper() != flight_filter.strip().upper():
            continue
        print("  " + format_report_row(row), file=out)
        shown += 1
    if not shown:
        print("  (no matching report rows)", file=out)

    print(
        "\n[2] GraphQL flightList — flightNid (correlate by STD time and airports;"
        " the flight query carries no flight number):",
        file=out,
    )
    # LEON rejects a zero-length flightList timeInterval ("Interval length out
    # of bounds" when start == end as bare dates), so the window is one day
    # wide — rows starting on the following day may appear and are harmless.
    from datetime import date as _date, timedelta as _timedelta

    next_day = (_date.fromisoformat(day) + _timedelta(days=1)).isoformat()
    flight_payload = executor.execute_query(
        build_flight_list_query(day, next_day, include_crew_function=False)
    )
    flight_list = flight_payload.get("flightList")
    if isinstance(flight_list, list) and flight_list:
        for flight in flight_list:
            if isinstance(flight, Mapping):
                print("  " + format_flight_list_row(flight), file=out)
    else:
        print("  (no flights)", file=out)

    print("\n[3] FTL dutyList — trNid values per crew member:", file=out)
    duty_payload = executor.execute_query(build_duty_list_query(day, day))
    duty_rows = _extract_duty_rows(duty_payload)
    if duty_rows:
        for duty in duty_rows:
            if isinstance(duty, Mapping):
                print("  " + format_duty_row(duty), file=out)
    else:
        print("  (no duties)", file=out)

    print(
        "\nIf [1] unique_id values match [2] flightNid and [3] trNid for the same"
        "\nphysical flight, the pipeline's join key is confirmed. If they differ,"
        "\ndo NOT patch a remapping ad hoc — record the finding and change the"
        "\njoin key in a reviewed slice.",
        file=out,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print the candidate LEON identifiers for one day side by side."
    )
    parser.add_argument("--date", required=True, help="UTC day to probe (YYYY-MM-DD)")
    parser.add_argument(
        "--flight",
        default=None,
        help="Optional flight number filter for the report rows (e.g. RSX331)",
    )
    arguments = parser.parse_args(argv)
    try:
        return run_probe(arguments.date, arguments.flight)
    except Exception as exc:  # noqa: BLE001 - CLI boundary: name the failure, no traceback spam
        print(f"Probe failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
