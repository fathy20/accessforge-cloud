"""STEP 4 — resolve Heavy for flights where LEON's augmentation value is UNKNOWN.

LEON leaves ``crewAugmentation`` empty for some duties.  The approved fallback:
a crew member is Heavy on such a flight only when they flew an immediately
neighbouring sector that

- chains airports with the current leg (an out-and-back or chained rotation),
- follows or precedes it with a break of ``0 <= break < 4h`` (3:59 connects,
  exactly 4:00 does not), and
- carries the same *operating* crew (PSN passengers excluded on both legs).

The pair belongs to one duty anchored on the first sector's UTC start date;
a short break across midnight is the SAME duty, so calendar dates are never
compared directly.  A member positioned as ``PSN`` on the current leg is No
immediately and no neighbour search runs.  Anything we cannot establish
resolves to NO, never to UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping, Sequence

from .crew_context import CrewContextEntry, CrewContextIndex, FlightContext
from .positions import CREW_SET_EXCLUDED_POSITIONS, crew_set_identity


# The break ceiling: two sectors count as one augmented rotation only strictly
# below this. ``break >= UNKNOWN_MAX_BREAK`` rejects, so exactly 4:00 fails.
UNKNOWN_MAX_BREAK = timedelta(hours=4)

# A neighbour starting further than this from the current leg's start can
# never share its duty window, whatever the break arithmetic says.
_DUTY_WINDOW_SPAN = timedelta(hours=24)

_PSN_POSITION = "psn"

# Slots that ride the flight without operating it — the shared exclusion set
# from positions.py (PSN/PAD positioning plus OBS/OBS2/STB), casefolded for
# the current-leg position checks below.
_NON_OPERATING_COMPARISON_POSITIONS = frozenset(
    value.casefold() for value in CREW_SET_EXCLUDED_POSITIONS
)

ResolutionReason = str


@dataclass(frozen=True)
class UnknownResolution:
    effective_heavy: bool
    resolved: bool
    reason: ResolutionReason


def build_rotation_index(
    index: CrewContextIndex,
) -> Mapping[str, tuple[FlightContext, ...]]:
    """Map every crew code to their flights, ordered by UTC start time.

    All members are indexed — including PSN passengers — because a member who
    rides PSN on one leg may operate the next; only the current-leg PSN check
    and the crew-set comparison exclude PSN.
    """

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
    # Case B — a PSN passenger is never augmented crew: NO immediately, and
    # deliberately without any neighbour search.
    if _is_psn(entry.position):
        return UnknownResolution(False, True, "PSN_POSITIONING")

    current_start = _parse_utc(current.start_time_utc)
    current_end = _parse_utc(current.end_time_utc)
    if current_start is None or current_end is None:
        return UnknownResolution(False, True, "MISSING_FLIGHT_TIMES")

    neighbours = _neighbours(rotation_index.get(normalized_code, ()), current)
    if not neighbours:
        return UnknownResolution(False, True, "NO_NEIGHBOUR_FLIGHT")

    reason: ResolutionReason = "NO_NEIGHBOUR_FLIGHT"
    for neighbour in neighbours:
        neighbour_start = _parse_utc(neighbour.start_time_utc)
        neighbour_end = _parse_utc(neighbour.end_time_utc)
        current_crew, neighbour_crew = _continuity_sets(
            current, neighbour, normalized_code
        )
        if neighbour_start is None or neighbour_end is None:
            reason = _weaker(reason, "MISSING_FLIGHT_TIMES")
            continue
        # Rotation continuity: the neighbour must chain airports with this
        # leg. Missing airport data cannot establish continuity — fail closed.
        if not _rotation_chained(current, neighbour):
            reason = _weaker(reason, "ROTATION_MISMATCH")
            continue
        break_duration = _break_between(
            current_start, current_end, neighbour_start, neighbour_end
        )
        if break_duration >= UNKNOWN_MAX_BREAK:
            # Midnight-safe duty window: a short break keeps the pair in one
            # duty regardless of calendar dates, so a failed break inside the
            # 24h window anchored on the current leg is a break problem.
            # DIFFERENT_DAY is reserved for genuinely disjoint days.
            genuinely_disjoint = (
                neighbour_start.date() != current_start.date()
                and abs(neighbour_start - current_start) > _DUTY_WINDOW_SPAN
            )
            reason = _weaker(
                reason, "DIFFERENT_DAY" if genuinely_disjoint else "BREAK_EXCEEDS_LIMIT"
            )
            continue
        if neighbour_crew != current_crew:
            reason = _weaker(reason, "CREW_SET_CHANGED")
            continue
        return UnknownResolution(True, True, "SAME_DAY_SHORT_BREAK_SAME_CREW")
    return UnknownResolution(False, True, reason)


# Ordered least-to-most informative so the reported reason is the closest near-miss.
_REASON_RANK = (
    "NO_NEIGHBOUR_FLIGHT",
    "MISSING_FLIGHT_TIMES",
    "DIFFERENT_DAY",
    "ROTATION_MISMATCH",
    "BREAK_EXCEEDS_LIMIT",
    "CREW_SET_CHANGED",
)


def _weaker(current: ResolutionReason, candidate: ResolutionReason) -> ResolutionReason:
    try:
        return candidate if _REASON_RANK.index(candidate) > _REASON_RANK.index(current) else current
    except ValueError:
        return candidate


def _rotation_chained(current: FlightContext, neighbour: FlightContext) -> bool:
    """An out-and-back or chained rotation shares an airport at the junction."""

    return (
        _same_airport(neighbour.departure_airport, current.arrival_airport)
        or _same_airport(neighbour.arrival_airport, current.departure_airport)
    )


def _continuity_sets(
    current: FlightContext,
    neighbour: FlightContext,
    subject_code: str,
) -> tuple[frozenset[str], frozenset[str]]:
    """The two comparable crew sets - CREW CONTINUITY, not role identity.

    ``crew_set_identity`` drops every positioning slot, and the comparison was a
    symmetric set equality. So a member who flew out as FO and rode home as PAD
    vanished from one side only, which broke the rotation not just for them but
    for EVERY member of it (live case RSX6077/RSX6078).

    The implemented rule, in full: for each leg, its OPERATING crew UNION
    everyone present on BOTH legs in any capacity UNION the subject. A member
    whose presence is continuous across the pair cannot be evidence of a crew
    change, whatever they were doing on each leg. Riders present on only ONE leg
    stay excluded - that part was always correct (RSX6081/RSX6082). The subject
    is added explicitly because the owner ruling names them; being on both legs
    is what made them a candidate in the first place.
    """

    on_both = _crew_codes(current.entries) & _crew_codes(neighbour.entries)
    anchor = on_both | {subject_code}
    return (
        rotation_crew_codes(current.entries) | anchor,
        rotation_crew_codes(neighbour.entries) | anchor,
    )


def _same_airport(left: str | None, right: str | None) -> bool:
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    normalized_left = left.strip().casefold()
    normalized_right = right.strip().casefold()
    return bool(normalized_left) and normalized_left == normalized_right


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


def _is_psn(position: str | None) -> bool:
    return isinstance(position, str) and position.strip().casefold() == _PSN_POSITION


def _crew_codes(entries: Sequence[CrewContextEntry]) -> frozenset[str]:
    return frozenset(
        entry.crew_code.strip().upper()
        for entry in entries
        if entry.crew_code and entry.crew_code.strip()
    )


def rotation_crew_codes(entries: Sequence[CrewContextEntry]) -> frozenset[str]:
    """The STEP-4 comparison set — the ROTATION crew identity.

    Shape adapter over positions.crew_set_identity — THE one crew-set
    definition (owner one-identity ruling 2026-08-17), shared with duty
    grouping in domain.py (NormalizedReportRow.rotation_crew_set). Excludes
    PSN, PAD (live case RSX6081/RSX6082: a PAD rider on one leg must not
    break the match), and OBS/OBS2/STB. Deliberately different from the
    TOTALS crew rule (CrewSlot.counts_in_totals, PSN-only, 2026-08-09 parity
    ruling) — do NOT unify the two (M-2 ruling 2026-08-18). Public: the
    flight-level facade in heavy.py iterates these members for STEP 4.
    """

    return crew_set_identity((entry.crew_code, entry.position) for entry in entries)


def _is_non_operating(position: str | None) -> bool:
    return (
        isinstance(position, str)
        and position.strip().casefold() in _NON_OPERATING_COMPARISON_POSITIONS
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
