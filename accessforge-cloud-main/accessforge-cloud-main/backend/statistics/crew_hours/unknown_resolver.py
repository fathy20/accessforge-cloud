"""STEP 4 — resolve Heavy for flights where LEON's augmentation value is UNKNOWN.

LEON leaves ``crewAugmentation`` empty for some duties.  The approved fallback is:
a crew member is Heavy on such a flight only when they flew a same-UTC-day
neighbouring sector with the same crew and a break no longer than four hours.
Anything we cannot establish resolves to NO, never to UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from .crew_context import CrewContextEntry, CrewContextIndex, FlightContext


# The break ceiling that still counts the two sectors as one augmented rotation.
UNKNOWN_MAX_BREAK = timedelta(hours=4)

ResolutionReason = str


@dataclass(frozen=True)
class UnknownResolution:
    effective_heavy: bool
    resolved: bool
    reason: ResolutionReason


def build_rotation_index(
    index: CrewContextIndex,
) -> Mapping[str, tuple[FlightContext, ...]]:
    """Map every crew code to their flights, ordered by UTC start time."""

    by_crew: dict[str, list[FlightContext]] = {}
    if not index.available:
        return {}
    for context in index.contexts.values():
        for code in _crew_codes(context.entries):
            by_crew.setdefault(code, []).append(context)
    return {
        code: tuple(sorted(contexts, key=_sort_key))
        for code, contexts in by_crew.items()
    }


def resolve_unknown_heavy(
    index: CrewContextIndex,
    rotation_index: Mapping[str, tuple[FlightContext, ...]],
    flight_nid: int | None,
    crew_code: str | None,
) -> UnknownResolution:
    """Apply STEP 4 for one crew member on one flight."""

    if not index.available or flight_nid is None or not crew_code:
        return UnknownResolution(False, False, "NO_FLIGHT_CONTEXT")
    normalized_code = crew_code.strip().upper()
    current = index.contexts.get(flight_nid)
    if current is None:
        return UnknownResolution(False, False, "NO_FLIGHT_CONTEXT")

    entry = _entry_for(current.entries, normalized_code)
    # Case A — we do not know what this person was doing on the flight, so NO.
    if entry is None or (entry.position is None and entry.function is None):
        return UnknownResolution(False, True, "UNKNOWN_POSITION")

    current_start = _parse_utc(current.start_time_utc)
    current_end = _parse_utc(current.end_time_utc)
    if current_start is None or current_end is None:
        return UnknownResolution(False, True, "MISSING_FLIGHT_TIMES")

    neighbours = _neighbours(rotation_index.get(normalized_code, ()), current)
    if not neighbours:
        return UnknownResolution(False, True, "NO_NEIGHBOUR_FLIGHT")

    current_crew = _crew_codes(current.entries)
    reason: ResolutionReason = "NO_NEIGHBOUR_FLIGHT"
    for neighbour in neighbours:
        neighbour_start = _parse_utc(neighbour.start_time_utc)
        neighbour_end = _parse_utc(neighbour.end_time_utc)
        if neighbour_start is None or neighbour_end is None:
            reason = "MISSING_FLIGHT_TIMES"
            continue
        # Different UTC day is an immediate NO — no break or crew check needed.
        if neighbour_start.date() != current_start.date():
            reason = _weaker(reason, "DIFFERENT_DAY")
            continue
        if _break_between(current_start, current_end, neighbour_start, neighbour_end) > UNKNOWN_MAX_BREAK:
            reason = _weaker(reason, "BREAK_EXCEEDS_LIMIT")
            continue
        if _crew_codes(neighbour.entries) != current_crew:
            reason = _weaker(reason, "CREW_SET_CHANGED")
            continue
        return UnknownResolution(True, True, "SAME_DAY_SHORT_BREAK_SAME_CREW")
    return UnknownResolution(False, True, reason)


# Ordered least-to-most informative so the reported reason is the closest near-miss.
_REASON_RANK = ("NO_NEIGHBOUR_FLIGHT", "MISSING_FLIGHT_TIMES", "DIFFERENT_DAY", "BREAK_EXCEEDS_LIMIT", "CREW_SET_CHANGED")


def _weaker(current: ResolutionReason, candidate: ResolutionReason) -> ResolutionReason:
    try:
        return candidate if _REASON_RANK.index(candidate) > _REASON_RANK.index(current) else current
    except ValueError:
        return candidate


def _neighbours(
    contexts: Sequence[FlightContext],
    current: FlightContext,
) -> tuple[FlightContext, ...]:
    """Return the immediately previous and next flight for this crew member."""

    ordered = [context for context in contexts]
    for position, context in enumerate(ordered):
        if context.flight_nid != current.flight_nid:
            continue
        found: list[FlightContext] = []
        if position > 0:
            found.append(ordered[position - 1])
        if position + 1 < len(ordered):
            found.append(ordered[position + 1])
        return tuple(found)
    return ()


def _break_between(
    current_start: datetime,
    current_end: datetime,
    neighbour_start: datetime,
    neighbour_end: datetime,
) -> timedelta:
    if neighbour_start >= current_end:
        return neighbour_start - current_end
    if neighbour_end <= current_start:
        return current_start - neighbour_end
    # Overlapping sectors leave no break at all.
    return timedelta(0)


def _entry_for(
    entries: Sequence[CrewContextEntry],
    crew_code: str,
) -> CrewContextEntry | None:
    for entry in entries:
        if entry.crew_code and entry.crew_code.strip().upper() == crew_code:
            return entry
    return None


def _crew_codes(entries: Sequence[CrewContextEntry]) -> frozenset[str]:
    return frozenset(
        entry.crew_code.strip().upper()
        for entry in entries
        if entry.crew_code and entry.crew_code.strip()
    )


def _sort_key(context: FlightContext) -> tuple[datetime, int]:
    parsed = _parse_utc(context.start_time_utc)
    return (parsed or datetime.max.replace(tzinfo=timezone.utc), context.flight_nid)


def _parse_utc(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith(("Z", "z")):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
