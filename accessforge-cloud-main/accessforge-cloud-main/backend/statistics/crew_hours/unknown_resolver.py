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
from .trace import HeavyTraceStep, format_break, step


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
    # The ordered record of what STEP 4 evaluated; see trace.HeavyTraceStep.
    trace: tuple[HeavyTraceStep, ...] = ()


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
        return UnknownResolution(
            False,
            False,
            "NO_FLIGHT_CONTEXT",
            (step("STEP_4_ROTATION", "no crew context index -> Heavy No"),),
        )
    normalized_code = crew_code.strip().upper()
    current = index.contexts.get(flight_nid)
    if current is None:
        return UnknownResolution(
            False,
            False,
            "NO_FLIGHT_CONTEXT",
            (
                step(
                    "STEP_4_ROTATION",
                    "this leg is absent from the flight-list context -> Heavy No",
                    crew_code=normalized_code,
                    flight_nid=flight_nid,
                ),
            ),
        )

    entry = _entry_for(current.entries, normalized_code)
    # Case A - we do not know what this person was doing on the flight, so NO.
    if entry is None or (entry.position is None and entry.function is None):
        return UnknownResolution(
            False,
            True,
            "UNKNOWN_POSITION",
            (
                step(
                    "STEP_4_ROTATION",
                    "no position or function for this member on this leg -> Heavy No",
                    crew_code=normalized_code,
                ),
            ),
        )
    # Case B - a PSN passenger is never augmented crew: NO immediately, and
    # deliberately without any neighbour search.
    if _is_psn(entry.position):
        return UnknownResolution(
            False,
            True,
            "PSN_POSITIONING",
            (
                step(
                    "STEP_4_ROTATION",
                    "member is PSN on this leg -> Heavy No, no neighbour search",
                    crew_code=normalized_code,
                    subject_position=entry.position,
                ),
            ),
        )

    current_start = _parse_utc(current.start_time_utc)
    current_end = _parse_utc(current.end_time_utc)
    if current_start is None or current_end is None:
        return UnknownResolution(
            False,
            True,
            "MISSING_FLIGHT_TIMES",
            (
                step(
                    "STEP_4_ROTATION",
                    "this leg has no usable UTC times -> Heavy No",
                    crew_code=normalized_code,
                    current_start_utc=current.start_time_utc,
                    current_end_utc=current.end_time_utc,
                ),
            ),
        )

    previous, upcoming = _previous_and_next(
        rotation_index.get(normalized_code, ()), current
    )
    # Pairing direction (owner ruling 2026-08-19): a leg whose duty began on an
    # earlier leg pairs BACKWARD. Forward is searched only when this leg is
    # itself first in its duty - nothing connected before it.
    first_in_duty = not _connects(current_start, current_end, previous)
    candidates: list[tuple[str, FlightContext]] = []
    if previous is not None:
        candidates.append(("backward", previous))
    if upcoming is not None and first_in_duty:
        candidates.append(("forward", upcoming))

    direction_note = (
        "first in duty: backward and forward"
        if first_in_duty
        else "mid-duty: backward only"
    )
    steps: list[HeavyTraceStep] = [
        step(
            "STEP_4_ROTATION",
            f"{len(candidates)} neighbour(s) searched, {direction_note}",
            crew_code=normalized_code,
            subject_position=entry.position,
            current_start_utc=current.start_time_utc,
            current_end_utc=current.end_time_utc,
            current_route=[current.departure_airport, current.arrival_airport],
            break_limit=format_break(UNKNOWN_MAX_BREAK),
        )
    ]

    if not candidates:
        steps.append(
            step("STEP_4_NEIGHBOUR", "no neighbouring sector for this member -> Heavy No")
        )
        return UnknownResolution(False, True, "NO_NEIGHBOUR_FLIGHT", tuple(steps))

    reason: ResolutionReason = "NO_NEIGHBOUR_FLIGHT"
    for direction, neighbour in candidates:
        neighbour_start = _parse_utc(neighbour.start_time_utc)
        neighbour_end = _parse_utc(neighbour.end_time_utc)
        current_crew, neighbour_crew = _continuity_sets(
            current, neighbour, normalized_code
        )

        def record(outcome: str, break_text: str | None = None) -> None:
            steps.append(
                step(
                    "STEP_4_NEIGHBOUR",
                    outcome,
                    direction=direction,
                    flight_nid=neighbour.flight_nid,
                    current_route=[current.departure_airport, current.arrival_airport],
                    neighbour_route=[
                        neighbour.departure_airport,
                        neighbour.arrival_airport,
                    ],
                    neighbour_start_utc=neighbour.start_time_utc,
                    neighbour_end_utc=neighbour.end_time_utc,
                    current_crew=sorted(current_crew),
                    neighbour_crew=sorted(neighbour_crew),
                    **({"break": break_text} if break_text is not None else {}),
                )
            )

        if neighbour_start is None or neighbour_end is None:
            record("MISSING_FLIGHT_TIMES: neighbour has no usable UTC times")
            reason = _weaker(reason, "MISSING_FLIGHT_TIMES")
            continue
        # Rotation continuity: a true out-and-back. Chaining onward to a third
        # airport is NOT a rotation (owner ruling 2026-08-19) - the original
        # rule is "flew out and came back". Missing airport data cannot
        # establish continuity - fail closed.
        if not _rotation_out_and_back(current, neighbour):
            record("ROTATION_MISMATCH: not an out-and-back pair")
            reason = _weaker(reason, "ROTATION_MISMATCH")
            continue
        break_duration = _break_between(
            current_start, current_end, neighbour_start, neighbour_end
        )
        break_text = format_break(break_duration)
        if break_duration >= UNKNOWN_MAX_BREAK:
            # Midnight-safe duty window: a short break keeps the pair in one
            # duty regardless of calendar dates, so a failed break inside the
            # 24h window anchored on the current leg is a break problem.
            # DIFFERENT_DAY is reserved for genuinely disjoint days.
            genuinely_disjoint = (
                neighbour_start.date() != current_start.date()
                and abs(neighbour_start - current_start) > _DUTY_WINDOW_SPAN
            )
            failed = "DIFFERENT_DAY" if genuinely_disjoint else "BREAK_EXCEEDS_LIMIT"
            record(
                f"{failed}: break {break_text} is not below "
                f"{format_break(UNKNOWN_MAX_BREAK)}",
                break_text,
            )
            reason = _weaker(reason, failed)
            continue
        if neighbour_crew != current_crew:
            record("CREW_SET_CHANGED: the compared crew sets differ", break_text)
            reason = _weaker(reason, "CREW_SET_CHANGED")
            continue
        record(
            "qualifies: out-and-back, break below the limit, same crew -> Heavy Yes",
            break_text,
        )
        return UnknownResolution(
            True, True, "SAME_DAY_SHORT_BREAK_SAME_CREW", tuple(steps)
        )
    return UnknownResolution(False, True, reason, tuple(steps))


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


def _rotation_out_and_back(current: FlightContext, neighbour: FlightContext) -> bool:
    """A rotation is a TRUE out-and-back: the pair returns where it started.

    Owner ruling 2026-08-19. The previous version accepted a shared airport in
    EITHER direction, so a chain onward (HRG->SSH then SSH->OPO) qualified and
    any same-direction pair with a stable roster and a short break was reported
    Heavy. Both clauses must hold now, which is symmetric: it reads the same
    whether the neighbour precedes or follows the current leg.
    """

    return (
        _same_airport(neighbour.departure_airport, current.arrival_airport)
        and _same_airport(neighbour.arrival_airport, current.departure_airport)
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

    The fix is to keep anyone present on BOTH legs, whatever they were doing on
    each: their presence is continuous, so it cannot be evidence of a crew
    change. Riders present on only ONE leg stay excluded - that part was always
    correct (RSX6081/RSX6082). The subject is added explicitly on both sides,
    which the owner ruling names directly; being on both legs is what made them
    a candidate in the first place.
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


def _previous_and_next(
    contexts: Sequence[FlightContext],
    current: FlightContext,
) -> tuple[FlightContext | None, FlightContext | None]:
    """The immediately previous and next flight for this crew member, in order."""

    ordered = list(contexts)
    for position, context in enumerate(ordered):
        if context.flight_nid != current.flight_nid:
            continue
        previous = ordered[position - 1] if position > 0 else None
        upcoming = ordered[position + 1] if position + 1 < len(ordered) else None
        return previous, upcoming
    return None, None


def _connects(
    current_start: datetime,
    current_end: datetime,
    neighbour: FlightContext | None,
) -> bool:
    """Whether a neighbour shares this leg's duty - the break gate alone.

    Used only to answer "is this leg first in its duty?", which decides whether
    the forward search runs at all. Airports and crew are deliberately not
    consulted: a leg preceded by a connected sector is mid-duty even if that
    sector turns out not to be a qualifying rotation partner.
    """

    if neighbour is None:
        return False
    neighbour_start = _parse_utc(neighbour.start_time_utc)
    neighbour_end = _parse_utc(neighbour.end_time_utc)
    if neighbour_start is None or neighbour_end is None:
        return False
    return (
        _break_between(current_start, current_end, neighbour_start, neighbour_end)
        < UNKNOWN_MAX_BREAK
    )


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
