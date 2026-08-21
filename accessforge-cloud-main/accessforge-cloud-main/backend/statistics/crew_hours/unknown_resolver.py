"""STEP 4 — resolve Heavy for flights where LEON's augmentation value is UNKNOWN.

LEON leaves ``crewAugmentation`` empty for some duties.  The approved fallback:
a crew member is Heavy on such a flight only when they flew an immediately
neighbouring sector that

- belongs to the SAME DUTY as the current leg, and
- sits a break of ``0 <= break < 4h`` away (3:59 connects, 4:00 does not), and
- carries continuous crew (see ``_continuity_sets``).

Airports are NOT a condition (owner ruling 2026-08-20, verified against live
rows). Two sectors of one duty flown by the same crew are the rotation; the
route is recorded in the trace so a verdict can be read, never judged on.

A DUTY is the maximal run of consecutive sectors joined by breaks below 4h.
The duty is built FIRST, then legs are judged inside it, and every other leg of
the duty is a candidate regardless of direction -- so a qualifying out-and-back
resolves identically from either end (owner rulings 2026-08-20). The duty's
identity is the UTC date its first sector started; calendar dates are never a
gate, only a label on an already-failed break. A member positioned as ``PSN``
on the current leg is No immediately and no search runs. Anything we cannot
establish resolves to NO, never to UNKNOWN.
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

    member_flights = rotation_index.get(normalized_code, ())
    duty = _duty_legs(member_flights, current)
    candidates = _duty_partners(duty, current)

    steps: list[HeavyTraceStep] = [
        step(
            "STEP_4_ROTATION",
            (
                f"duty of {len(duty)} sector(s) anchored on {_duty_anchor_date(duty)}; "
                f"{len(candidates)} partner(s) to judge, direction irrelevant"
            ),
            crew_code=normalized_code,
            subject_position=entry.position,
            current_start_utc=current.start_time_utc,
            current_end_utc=current.end_time_utc,
            current_route=[current.departure_airport, current.arrival_airport],
            duty_anchor_utc_date=_duty_anchor_date(duty),
            duty_sectors=len(duty),
            break_limit=format_break(UNKNOWN_MAX_BREAK),
        )
    ]

    if not candidates:
        # Alone in its duty. The sector across the duty boundary is examined
        # ONLY to explain why it is not a partner, never to pair with.
        reason, trace = _lone_leg_reason(
            member_flights, current, current_start, current_end, steps
        )
        return UnknownResolution(False, True, reason, trace)

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
        # Airports do NOT gate the rotation (owner ruling 2026-08-20, verified
        # against live rows: SSH->HRG->OPO on 22-06 and HRG->SSH->OPO on 23-06
        # are both Heavy). Two sectors of one duty flown by the same crew ARE
        # the rotation; where they went is recorded in the trace, not judged.
        # This RETRACTS the 2026-08-19 out-and-back tightening.
        break_duration = _break_between(
            current_start, current_end, neighbour_start, neighbour_end
        )
        break_text = format_break(break_duration)
        if break_duration >= UNKNOWN_MAX_BREAK:
            # The break is the ONLY gate. The date comparison picks the label
            # and never causes the rejection (owner ruling 4, 2026-08-20).
            failed = _break_failure_reason(current_start, neighbour_start)
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
            "qualifies: same duty, break below the limit, same crew -> Heavy Yes",
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
    "BREAK_EXCEEDS_LIMIT",
    "CREW_SET_CHANGED",
)


def _weaker(current: ResolutionReason, candidate: ResolutionReason) -> ResolutionReason:
    try:
        return candidate if _REASON_RANK.index(candidate) > _REASON_RANK.index(current) else current
    except ValueError:
        return candidate


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


def _position_of(contexts: Sequence[FlightContext], current: FlightContext) -> int | None:
    for position, context in enumerate(contexts):
        if context.flight_nid == current.flight_nid:
            return position
    return None


def _consecutive_break(earlier: FlightContext, later: FlightContext) -> timedelta:
    """The gap between two adjacent sectors, or "infinite" if either lacks times.

    Unparseable times break the duty rather than extending it - continuity that
    cannot be established is never assumed.
    """

    earlier_start = _parse_utc(earlier.start_time_utc)
    earlier_end = _parse_utc(earlier.end_time_utc)
    later_start = _parse_utc(later.start_time_utc)
    later_end = _parse_utc(later.end_time_utc)
    if None in (earlier_start, earlier_end, later_start, later_end):
        return timedelta.max
    return _break_between(earlier_start, earlier_end, later_start, later_end)


def _duty_legs(
    contexts: Sequence[FlightContext],
    current: FlightContext,
) -> tuple[FlightContext, ...]:
    """Every sector of the duty this leg belongs to, in UTC order.

    A duty is the maximal run of consecutive sectors joined by breaks strictly
    below UNKNOWN_MAX_BREAK. Calendar dates are never consulted: a rotation
    departing 21:50 and landing 03:35(+1) is ONE duty (owner ruling 2, 2026-08-20).

    Anchoring the search on the duty rather than on the two immediate neighbours
    is what makes it symmetric - see _duty_partners.
    """

    ordered = list(contexts)
    position = _position_of(ordered, current)
    if position is None:
        return ()
    start = position
    while start > 0 and _consecutive_break(ordered[start - 1], ordered[start]) < UNKNOWN_MAX_BREAK:
        start -= 1
    end = position
    while (
        end + 1 < len(ordered)
        and _consecutive_break(ordered[end], ordered[end + 1]) < UNKNOWN_MAX_BREAK
    ):
        end += 1
    return tuple(ordered[start : end + 1])


def _duty_anchor_date(duty: Sequence[FlightContext]) -> str | None:
    """The duty's identity: the UTC date its FIRST sector started."""

    if not duty:
        return None
    anchor = _parse_utc(duty[0].start_time_utc)
    return anchor.date().isoformat() if anchor else None


def _duty_partners(
    duty: Sequence[FlightContext],
    current: FlightContext,
) -> tuple[tuple[str, FlightContext], ...]:
    """Every other leg of the duty, nearest first, backward before forward.

    Direction carries no authority here (owner ruling 3, 2026-08-20): it only
    orders the search so the reported near-miss reason is the closest one, and
    it labels the trace. Because both ends of a pair see each other as
    candidates, a qualifying out-and-back resolves the same from either leg -
    which is exactly what RSX6077/RSX6078 needed.
    """

    position = _position_of(list(duty), current)
    if position is None:
        return ()
    partners: list[tuple[str, FlightContext]] = []
    for offset in range(1, len(duty)):
        for index, direction in ((position - offset, "backward"), (position + offset, "forward")):
            if 0 <= index < len(duty) and index != position:
                partners.append((direction, duty[index]))
    return tuple(partners)


def _break_failure_reason(current_start: datetime, neighbour_start: datetime) -> str:
    """Label a break that already failed the 4h gate; it never causes failure.

    DIFFERENT_DAY distinguishes "genuinely the next duty" from "same day, break
    simply too long" (owner ruling 4, 2026-08-20).
    """

    return (
        "DIFFERENT_DAY"
        if neighbour_start.date() != current_start.date()
        else "BREAK_EXCEEDS_LIMIT"
    )


def _adjacent_outside_duty(
    contexts: Sequence[FlightContext],
    current: FlightContext,
) -> tuple[str, FlightContext] | None:
    """The nearest sector on either side of a single-leg duty, for the reason only."""

    ordered = list(contexts)
    position = _position_of(ordered, current)
    if position is None:
        return None
    options: list[tuple[timedelta, str, FlightContext]] = []
    if position > 0:
        options.append((_consecutive_break(ordered[position - 1], current), "backward", ordered[position - 1]))
    if position + 1 < len(ordered):
        options.append((_consecutive_break(current, ordered[position + 1]), "forward", ordered[position + 1]))
    if not options:
        return None
    _, direction, neighbour = min(options, key=lambda option: option[0])
    return direction, neighbour


def _lone_leg_reason(
    contexts: Sequence[FlightContext],
    current: FlightContext,
    current_start: datetime,
    current_end: datetime,
    steps: list[HeavyTraceStep],
) -> tuple[ResolutionReason, tuple[HeavyTraceStep, ...]]:
    """Why a leg alone in its duty has no rotation partner."""

    adjacent = _adjacent_outside_duty(contexts, current)
    if adjacent is None:
        steps.append(
            step("STEP_4_NEIGHBOUR", "this member flew no other sector at all -> Heavy No")
        )
        return "NO_NEIGHBOUR_FLIGHT", tuple(steps)

    direction, neighbour = adjacent
    neighbour_start = _parse_utc(neighbour.start_time_utc)
    neighbour_end = _parse_utc(neighbour.end_time_utc)
    if neighbour_start is None or neighbour_end is None:
        steps.append(
            step(
                "STEP_4_NEIGHBOUR",
                "MISSING_FLIGHT_TIMES: the adjacent sector has no usable UTC times",
                direction=direction,
                flight_nid=neighbour.flight_nid,
            )
        )
        return "MISSING_FLIGHT_TIMES", tuple(steps)

    gap = _break_between(current_start, current_end, neighbour_start, neighbour_end)
    failed = _break_failure_reason(current_start, neighbour_start)
    steps.append(
        step(
            "STEP_4_NEIGHBOUR",
            f"{failed}: the nearest {direction} sector is {format_break(gap)} away, "
            "outside this duty -> Heavy No",
            direction=direction,
            flight_nid=neighbour.flight_nid,
            neighbour_route=[neighbour.departure_airport, neighbour.arrival_airport],
            neighbour_start_utc=neighbour.start_time_utc,
            neighbour_end_utc=neighbour.end_time_utc,
            **{"break": format_break(gap)},
        )
    )
    return failed, tuple(steps)


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
