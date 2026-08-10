"""Sanitized Crew Hours parity fixtures.

Only business fields needed by the regression contract are retained.  These
fixtures contain no LEON payload envelopes, tokens, credentials, or journey log
objects.
"""

from __future__ import annotations

from typing import Sequence


def report_leg(
    flight_number: str,
    *,
    flight_date: str,
    off: str,
    on: str,
    crew_codes: Sequence[str],
    positions: Sequence[str] | None,
    block_time: str,
) -> dict[str, object]:
    row: dict[str, object] = {
        "scope_row_unique_id": f"fixture-{flight_number}",
        "flightNo": flight_number,
        "date_STD_log_UTC": flight_date,
        "JL_STD_UTC": off,
        "JL_STA_UTC": on,
        "crew_codes": list(crew_codes),
        "blockTimeJourneyLog": block_time,
    }
    if positions is not None:
        row["crew_position_names"] = list(positions)
    return row


NORMAL_OPERATING_SECTOR = report_leg(
    "RSX-NORMAL",
    flight_date="15-06-2026",
    off="08:00",
    on="09:30",
    crew_codes=("OPERATING",),
    positions=("CPT",),
    block_time="01:30",
)

PSN_ONLY_SECTOR = report_leg(
    "RSX-PSN",
    flight_date="15-06-2026",
    off="10:00",
    on="12:00",
    crew_codes=("PASSENGER",),
    positions=("PSN",),
    block_time="02:00",
)

MIXED_OPERATING_PSN_SECTOR = report_leg(
    "RSX-MIXED",
    flight_date="15-06-2026",
    off="13:00",
    on="15:15",
    crew_codes=("OPERATING", "PASSENGER"),
    positions=("FO", "PSN"),
    block_time="02:15",
)

EXPLICIT_TRN_SECTOR = {
    "scope_row_unique_id": "fixture-trn",
    "flightNo": "RSX-TRN",
    "date_STD_log_UTC": "16-06-2026",
    "JL_STD_UTC": "08:00",
    "JL_STA_UTC": "08:00",
    "crew_codes": ["TRAINING"],
    "crew_names": ["Training Fixture"],
    "crew_position_names": ["CPT"],
    "blockTimeJourneyLog": "",
}

ACCUMULATED_DURATION_ROWS = tuple(
    report_leg(
        f"RSX-LONG-{index}",
        flight_date=f"{index:02d}-06-2026",
        off="08:00",
        on="09:00",
        crew_codes=("LONG-HOURS",),
        positions=("CPT",),
        block_time=value,
    )
    for index, value in enumerate(("57:35", "88:30", "94:40"), start=1)
)


def connected_boundary_pair(
    gap_minutes: int,
    *,
    second_codes: Sequence[str] = ("A", "B"),
    reverse_second_order: bool = False,
) -> tuple[dict[str, object], dict[str, object]]:
    hour, minute = divmod(22 * 60 + gap_minutes, 60)
    second_date = "30-06-2026" if hour < 24 else "01-07-2026"
    second_off = f"{hour % 24:02d}:{minute:02d}"
    on_hour, on_minute = divmod((hour * 60 + minute + 60) % (24 * 60), 60)
    second_on = f"{on_hour:02d}:{on_minute:02d}"
    ordered_codes = tuple(reversed(second_codes)) if reverse_second_order else tuple(second_codes)
    return (
        report_leg(
            f"RSX-GAP-{gap_minutes}-OUT",
            flight_date="30-06-2026",
            off="20:00",
            on="22:00",
            crew_codes=("A", "B"),
            positions=("CPT", "FO"),
            block_time="02:00",
        ),
        report_leg(
            f"RSX-GAP-{gap_minutes}-BACK",
            flight_date=second_date,
            off=second_off,
            on=second_on,
            crew_codes=ordered_codes,
            positions=("FO", "CPT") if reverse_second_order else ("CPT", "FO"),
            block_time="01:00",
        ),
    )


# Verified live LEON boundary A, sanitized to the business fields approved in the task.
LIVE_BOUNDARY_A_CODES = (
    "AAM", "FTA", "LAZ", "MMA", "MMM", "MMR", "MQE",
    "MSA", "NADG", "OAM", "SAA", "SAL", "YOM",
)
LIVE_BOUNDARY_A_POSITIONS = (
    "CPT", "FO", "FA1", "FA2", "FA3", "FA4", "ENG1",
    "PAD", "PAD", "PAD", "PAD", "PAD", "PAD",
)
LIVE_BOUNDARY_A = (
    report_leg(
        "RSX331",
        flight_date="30-06-2026",
        off="17:20",
        on="23:05",
        crew_codes=LIVE_BOUNDARY_A_CODES,
        positions=LIVE_BOUNDARY_A_POSITIONS,
        block_time="05:45",
    ),
    report_leg(
        "RSX332",
        flight_date="01-07-2026",
        off="00:00",
        on="05:40",
        crew_codes=LIVE_BOUNDARY_A_CODES,
        positions=LIVE_BOUNDARY_A_POSITIONS,
        block_time="05:40",
    ),
)


# Verified live LEON boundary B.  No per-member positions were supplied for this
# case, so none are invented in the fixture.
LIVE_BOUNDARY_B_CODES = ("AMO", "ELS", "GOMS", "KHD", "MMW", "MSD", "MSH")
LIVE_BOUNDARY_B = (
    report_leg(
        "RSX123",
        flight_date="30-06-2026",
        off="23:50",
        on="02:25",
        crew_codes=LIVE_BOUNDARY_B_CODES,
        positions=None,
        block_time="02:35",
    ),
    report_leg(
        "RSX124",
        flight_date="01-07-2026",
        off="03:25",
        on="06:30",
        crew_codes=LIVE_BOUNDARY_B_CODES,
        positions=None,
        block_time="03:05",
    ),
)


# Source: docs/architecture/crew-hours-source-decision.md,
# "June 2026 Reference Reconciliation", Reference column.  Only values needed
# by assertions are retained; TRN is deliberately outside the numeric grand total.
JUNE_COCKPIT_REFERENCE_VALUES = ("90:20", "94:40", "0:00", "TRN")
JUNE_COCKPIT_REFERENCE_NUMERIC_GRAND_TOTAL = "185:00"
