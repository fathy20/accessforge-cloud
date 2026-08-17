"""Crew Hours business normalization and month-attribution rules."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import re
from typing import Any, Mapping, Sequence

from .errors import LeonContractError
from .positions import crew_set_identity


READ_BUFFER_DAYS = 2
CONNECTED_DUTY_BREAK = timedelta(hours=4)
PSN_POSITION = "PSN"
TRN_TOTAL = "TRN"
_SOURCE_DATE_PATTERN = re.compile(r"\d{2}-\d{2}-\d{4}")
_ISO_DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")
_UTC_TIME_PATTERN = re.compile(r"(?P<hour>\d{2}):(?P<minute>\d{2})")


@dataclass(frozen=True)
class CrewSlot:
    code: str
    name: str | None
    position: str | None
    source_index: int

    @property
    def is_operating(self) -> bool:
        return (self.position or "").strip().upper() != PSN_POSITION


@dataclass(frozen=True)
class NormalizedReportRow:
    source: Mapping[str, Any]
    crew: tuple[CrewSlot, ...]
    source_date: date | None
    off_utc: datetime | None
    on_utc: datetime | None
    names_misaligned: bool
    positions_misaligned: bool

    @property
    def arrays_misaligned(self) -> bool:
        return self.names_misaligned or self.positions_misaligned

    @property
    def operating_crew_set(self) -> frozenset[str]:
        # Duty-grouping identity: THE shared crew-set definition (owner ruling
        # 2026-08-17). Riders and non-operating cockpit slots never split a
        # duty. Distinct from ``is_operating`` above, which keeps its settled
        # PSN-only meaning for per-member numeric totals.
        return crew_set_identity((slot.code, slot.position) for slot in self.crew)


def buffered_query_dates(from_date: str, to_date: str) -> tuple[str, str]:
    """Return the bounded UTC read window surrounding an already-valid period."""

    start = _parse_iso_period_date(from_date)
    end = _parse_iso_period_date(to_date)
    if start > end:
        raise LeonContractError("Crew Hours period start must not be after end date.")
    buffer = timedelta(days=READ_BUFFER_DAYS)
    return (start - buffer).isoformat(), (end + buffer).isoformat()


def is_trn_total(value: object) -> bool:
    """TRN is an authoritative text sentinel, never a numeric zero."""

    return value == TRN_TOTAL


def normalize_report_row(row: Mapping[str, Any]) -> NormalizedReportRow:
    """Pair crew arrays by source index and normalize the approved UTC columns."""

    if not isinstance(row, Mapping):
        raise LeonContractError("LEON MCP report row had an invalid shape.")
    raw_codes = row.get("crew_codes")
    if not isinstance(raw_codes, list) or any(not isinstance(code, str) for code in raw_codes):
        raise LeonContractError("LEON MCP report row had invalid crew_codes.")

    names, names_misaligned = _aligned_optional_strings(row, "crew_names", len(raw_codes))
    positions, positions_misaligned = _aligned_optional_strings(
        row,
        "crew_position_names",
        len(raw_codes),
    )
    crew: list[CrewSlot] = []
    seen_codes: set[str] = set()
    for index, raw_code in enumerate(raw_codes):
        code = raw_code.strip()
        if not code or code in seen_codes:
            continue
        seen_codes.add(code)
        crew.append(
            CrewSlot(
                code=code,
                name=_indexed(names, index),
                position=_indexed(positions, index),
                source_index=index,
            )
        )

    source_date = _optional_source_date(row.get("date_STD_log_UTC"))
    off_utc, on_utc = _optional_leg_window(
        source_date,
        row.get("JL_STD_UTC"),
        row.get("JL_STA_UTC"),
    )
    return NormalizedReportRow(
        source=row,
        crew=tuple(crew),
        source_date=source_date,
        off_utc=off_utc,
        on_utc=on_utc,
        names_misaligned=names_misaligned,
        positions_misaligned=positions_misaligned,
    )


def select_rows_for_period(
    rows: Sequence[Mapping[str, Any]],
    from_date: str,
    to_date: str,
) -> list[Mapping[str, Any]]:
    """Attribute connected duties to their first leg, then select the requested period.

    Rows are returned in LEON source order.  Rows lacking the optional date/time
    columns remain included for compatibility with the required-column contract;
    fetched live reports request all three approved UTC columns.
    """

    period_start = _parse_iso_period_date(from_date)
    period_end = _parse_iso_period_date(to_date)
    if period_start > period_end:
        raise LeonContractError("Crew Hours period start must not be after end date.")

    normalized = [(index, normalize_report_row(row)) for index, row in enumerate(rows)]
    selected_indices: set[int] = set()
    duty_candidates: dict[frozenset[str], list[tuple[int, NormalizedReportRow]]] = defaultdict(list)

    for index, normalized_row in normalized:
        if (
            normalized_row.off_utc is not None
            and normalized_row.on_utc is not None
            and normalized_row.operating_crew_set
        ):
            duty_candidates[normalized_row.operating_crew_set].append((index, normalized_row))
            continue

        attribution_date = (
            normalized_row.off_utc.date()
            if normalized_row.off_utc is not None
            else normalized_row.source_date
        )
        if attribution_date is None or period_start <= attribution_date <= period_end:
            selected_indices.add(index)

    for crew_rows in duty_candidates.values():
        ordered = sorted(
            crew_rows,
            key=lambda item: (item[1].off_utc or datetime.min.replace(tzinfo=timezone.utc), item[0]),
        )
        duty: list[tuple[int, NormalizedReportRow]] = []
        for candidate in ordered:
            if not duty:
                duty = [candidate]
                continue
            previous = duty[-1][1]
            current = candidate[1]
            break_duration = current.off_utc - previous.on_utc
            if timedelta(0) <= break_duration < CONNECTED_DUTY_BREAK:
                duty.append(candidate)
                continue
            _select_duty(duty, period_start, period_end, selected_indices)
            duty = [candidate]
        _select_duty(duty, period_start, period_end, selected_indices)

    return [row for index, row in enumerate(rows) if index in selected_indices]


def _select_duty(
    duty: Sequence[tuple[int, NormalizedReportRow]],
    period_start: date,
    period_end: date,
    selected_indices: set[int],
) -> None:
    if not duty:
        return
    first_off = duty[0][1].off_utc
    if first_off is None:
        return
    if period_start <= first_off.date() <= period_end:
        selected_indices.update(index for index, _ in duty)


def _aligned_optional_strings(
    row: Mapping[str, Any],
    key: str,
    expected_length: int,
) -> tuple[list[str | None] | None, bool]:
    if key not in row:
        return None, False
    value = row[key]
    if not isinstance(value, list) or len(value) != expected_length:
        return None, True
    normalized = [
        item.strip() if isinstance(item, str) and item.strip() else None
        for item in value
    ]
    return normalized, False


def _indexed(values: list[str | None] | None, index: int) -> str | None:
    if values is None or index >= len(values):
        return None
    return values[index]


def _parse_iso_period_date(value: str) -> date:
    if not isinstance(value, str) or _ISO_DATE_PATTERN.fullmatch(value) is None:
        raise LeonContractError("Crew Hours periods must use strict YYYY-MM-DD dates.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LeonContractError("Crew Hours periods must use valid calendar dates.") from exc


def _optional_source_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise LeonContractError("LEON MCP report Date ADEP [JL][UTC] was invalid.")
    normalized = value.strip()
    try:
        if _SOURCE_DATE_PATTERN.fullmatch(normalized):
            return datetime.strptime(normalized, "%d-%m-%Y").date()
        if _ISO_DATE_PATTERN.fullmatch(normalized):
            return date.fromisoformat(normalized)
    except ValueError as exc:
        raise LeonContractError("LEON MCP report Date ADEP [JL][UTC] was invalid.") from exc
    raise LeonContractError("LEON MCP report Date ADEP [JL][UTC] was invalid.")


def _optional_leg_window(
    source_date: date | None,
    off_value: Any,
    on_value: Any,
) -> tuple[datetime | None, datetime | None]:
    if source_date is None or off_value in (None, "") or on_value in (None, ""):
        return None, None
    off_time = _parse_utc_time(off_value, "BLOFF")
    on_time = _parse_utc_time(on_value, "BLON")
    off_utc = datetime.combine(source_date, off_time, tzinfo=timezone.utc)
    on_utc = datetime.combine(source_date, on_time, tzinfo=timezone.utc)
    if on_utc < off_utc:
        on_utc += timedelta(days=1)
    return off_utc, on_utc


def _parse_utc_time(value: Any, label: str) -> time:
    if not isinstance(value, str):
        raise LeonContractError(f"LEON MCP report {label} [JL][UTC] was invalid.")
    match = _UTC_TIME_PATTERN.fullmatch(value.strip())
    if match is None:
        raise LeonContractError(f"LEON MCP report {label} [JL][UTC] was invalid.")
    hour = int(match.group("hour"))
    minute = int(match.group("minute"))
    if hour > 23 or minute > 59:
        raise LeonContractError(f"LEON MCP report {label} [JL][UTC] was invalid.")
    return time(hour=hour, minute=minute)
