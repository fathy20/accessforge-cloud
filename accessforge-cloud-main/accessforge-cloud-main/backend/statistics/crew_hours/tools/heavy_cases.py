"""Render the four reviewed Heavy cases from sanitized fixtures, with traces.

The June 2026 UI review produced four rotations whose verdicts were wrong or
unexplained. This tool rebuilds each one from synthetic rows - no LEON call, no
credentials, no real crew names or person codes - runs them through the real
report pipeline, and prints the verdict, the reason, the badge, and the full
decision trace for every leg.

It is the offline counterpart to re-running the live report: if a rule regresses,
this prints the wrong answer without needing a screenshot to notice.

Usage:

    python -m backend.statistics.crew_hours.tools.heavy_cases
    python -m backend.statistics.crew_hours.tools.heavy_cases --case B
    python -m backend.statistics.crew_hours.tools.heavy_cases --no-trace

The live June 2026 report, for comparison against the screenshots:

    GET /api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30&position=All

    curl -s -H "Authorization: Bearer $TOKEN" \\
      "http://localhost:8000/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30&position=All"
"""

from __future__ import annotations

import argparse
from typing import Any, Sequence

from ..augmented import AugmentedIndex
from ..crew_context import CrewContextEntry, CrewContextIndex, FlightContext
from ..mcp_report import OfficialMcpReport
from ..service import _build_mcp_report_response

_CABIN_PREFIXES = ("FA", "SFA", "EFA", "IFA")


def _pos_type_for(position: str) -> str:
    return "CABIN" if position.strip().upper().startswith(_CABIN_PREFIXES) else "COCKPIT"


def _entries(codes_positions) -> tuple[CrewContextEntry, ...]:
    return tuple(
        CrewContextEntry(
            pos_type=_pos_type_for(position),
            position=position,
            training_type=None,
            crew_code=code,
            function=None,
        )
        for code, position in codes_positions
    )


def _leg(
    unique_id: int,
    flight_number: str,
    adep: str | None,
    ades: str | None,
    start: str,
    end: str,
    codes_positions,
) -> tuple[dict[str, Any], FlightContext]:
    codes = [code for code, _ in codes_positions]
    row = {
        "scope_row_unique_id": f"row-{unique_id}",
        "unique_id": unique_id,
        "flightNo": flight_number,
        "crew_codes": codes,
        "crew_names": [f"Crew {code}" for code in codes],
        "crew_position_names": [position for _, position in codes_positions],
        "acftType": "B738 - 737-800",
        "blockTimeJourneyLog": "01:30",
        "jl_adep_preferred_code": adep,
        "jl_ades_preferred_code": ades,
        "JL_STD_UTC": start,
        "JL_STA_UTC": end,
    }
    context = FlightContext(
        flight_nid=unique_id,
        start_time_utc=start,
        end_time_utc=end,
        flight_tags=(),
        entries=_entries(codes_positions),
        departure_airport=adep,
        arrival_airport=ades,
    )
    return row, context


CASES: dict[str, dict[str, Any]] = {
    "A": {
        "title": "SVX rotation, ICAO-coded (D-1) - expect Yes on both, SVX_AIRPORT, no badge",
        "legs": [
            _leg(801, "RSX331", "HESH", "USSS", "2026-06-16T17:15:00Z", "2026-06-16T22:35:00Z",
                 [("C1", "CPT"), ("C2", "FO")]),
            _leg(802, "RSX332", "USSS", "HESH", "2026-06-16T23:50:00Z", "2026-06-17T06:00:00Z",
                 [("C1", "CPT"), ("C2", "FO")]),
        ],
    },
    "B": {
        "title": "Own PAD slot on the return (D-2) - expect Yes on both for every member, badged",
        "legs": [
            _leg(901, "RSX6077", "HRG", "LIS", "2026-06-14T14:25:00Z", "2026-06-14T20:40:00Z",
                 [("C1", "CPT"), ("C2", "FO"), ("C3", "FA1")]),
            _leg(902, "RSX6078", "LIS", "HRG", "2026-06-14T21:50:00Z", "2026-06-15T03:35:00Z",
                 [("C1", "CPT"), ("C2", "PAD"), ("C3", "FA1")]),
        ],
    },
    "C": {
        "title": "Chain onward, not a return - expect No on both, ROTATION_MISMATCH, no badge",
        "legs": [
            _leg(1001, "RSX8891", "HRG", "SSH", "2026-06-18T06:00:00Z", "2026-06-18T07:10:00Z",
                 [("C1", "CPT"), ("C2", "FO")]),
            _leg(1002, "RSX6083", "SSH", "OPO", "2026-06-18T08:00:00Z", "2026-06-18T13:30:00Z",
                 [("C1", "CPT"), ("C2", "FO")]),
        ],
    },
    "D": {
        "title": "Rotation never returns - expect No on both, no badge",
        "legs": [
            _leg(1101, "RSX6081", "HRG", "OPO", "2026-06-22T15:00:00Z", "2026-06-22T21:00:00Z",
                 [("C1", "CPT"), ("C2", "FO")]),
            _leg(1102, "RSX6084", "OPO", "SSH", "2026-06-23T08:00:00Z", "2026-06-23T12:00:00Z",
                 [("C1", "CPT"), ("C2", "FO")]),
        ],
    },
}


def _render(name: str, case: dict[str, Any], *, show_trace: bool) -> None:
    rows = [row for row, _ in case["legs"]]
    contexts = [context for _, context in case["legs"]]
    totals = {code: "10:00" for row in rows for code in row["crew_codes"]}

    response = _build_mcp_report_response(
        OfficialMcpReport(totals, rows),
        from_date="2026-06-01",
        to_date="2026-06-30",
        position="All",
        crew_member=None,
        # LEON is silent for all four cases: the FTL index exists, holds no value.
        augmented_index=AugmentedIndex(True, {}, 0, 0, {}),
        crew_context_index=CrewContextIndex(
            available=True,
            by_flight={context.flight_nid: context.entries for context in contexts},
            contexts={context.flight_nid: context for context in contexts},
        ),
    )

    print(f"\n{'=' * 78}\nCASE {name} - {case['title']}\n{'=' * 78}")
    for member in response.crew_members:
        for flight in member.flights:
            verdict = {True: "Yes", False: "No", None: "UNKNOWN"}[flight.augmented_heavy]
            badge = "BADGE" if flight.unknown_resolved else "no badge"
            print(
                f"\n  {member.person_code:<4} {flight.flight_number:<9} "
                f"{flight.departure_airport or '--':<5}->{flight.arrival_airport or '--':<5} "
                f"| Heavy {verdict:<7} | {flight.heavy_reason:<22} | "
                f"{flight.heavy_source:<11} | {badge}"
                + (f" | {flight.unknown_resolution_reason}" if flight.unknown_resolution_reason else "")
            )
            if show_trace:
                for step in flight.heavy_trace:
                    print(f"      {step.step:<24} {step.outcome}")
                    for key, value in step.inputs.items():
                        print(f"          {key} = {value}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", choices=sorted(CASES), help="Render one case only.")
    parser.add_argument(
        "--no-trace", action="store_true", help="Verdict lines only, without the trace."
    )
    args = parser.parse_args(argv)

    selected = [args.case] if args.case else sorted(CASES)
    for name in selected:
        _render(name, CASES[name], show_trace=not args.no_trace)
    print(
        "\nAll four cases are synthetic. To compare against the live screenshots, "
        "re-run the June 2026 report:\n"
        "  GET /api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30&position=All\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
