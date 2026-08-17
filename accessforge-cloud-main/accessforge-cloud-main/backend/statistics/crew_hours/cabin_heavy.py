"""Cabin Augmented (Heavy) classification — separate from cockpit by design.

Cockpit and cabin used to share one function, which made it impossible to change
one without risking the other.  They are split here:

  * ``classify_cockpit_heavy``  — the existing cockpit rule, frozen verbatim.
  * ``classify_cabin_augmented_heavy`` — the corrected cabin rule.

The correction that matters: SVX and EVN are **airport codes**, checked against
ADEP/ADES.  The previous implementation looked for them in ``flightTags``, and
no flight in the operator's data carries any tag at all — so those two rules had
never once fired.

Both functions are pure: no network, no clock, no I/O.  Callers supply adjacent
legs for the UNKNOWN rule rather than the function fetching them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Sequence

from .crew_context import CrewContextEntry
from .heavy import operating_cockpit_count
from .positions import HEAVY_CABIN_THRESHOLD, HEAVY_COCKPIT_THRESHOLD

# Airport codes, matched against ADEP/ADES — not flight tags.
SVX_AIRPORT = "SVX"
EVN_AIRPORT = "EVN"

# Positions removed from the cabin count before the threshold is applied.
CABIN_EXCLUDED_POSITIONS = frozenset({"SP", "OPS"})

# The agreed trainee marker, usable only once LEON exposes a Function field:
# Position == "SFA" AND Function == "TRN".  Position alone is not sufficient.
TRAINEE_POSITION = "SFA"
TRAINEE_FUNCTION = "TRN"

UNKNOWN_MAX_BREAK = timedelta(hours=4)

FUNCTION_UNAVAILABLE_NOTE = "Function data unavailable — TRN exclusion not applied"


@dataclass(frozen=True)
class CabinCrewMember:
    crew_code: str | None = None
    position: str | None = None
    # None means "LEON did not supply it", never "confirmed not a trainee".
    function: str | None = None


@dataclass(frozen=True)
class AdjacentLeg:
    start_time_utc: datetime | None = None
    end_time_utc: datetime | None = None
    cabin_crew: tuple[CabinCrewMember, ...] = ()


@dataclass(frozen=True)
class CabinFlight:
    adep: str | None = None
    ades: str | None = None
    start_time_utc: datetime | None = None
    end_time_utc: datetime | None = None
    aircraft_registration: str | None = None
    # True when LEON's augmented reference dataset has no value for this
    # flight/crew member, which is what triggers the pairing rule.
    is_unknown: bool = False
    adjacent_legs: tuple[AdjacentLeg, ...] = ()


def classify_cockpit_heavy(
    flight: CabinFlight,
    cockpit_crew_list: Sequence[CrewContextEntry],
) -> tuple[bool, str]:
    """Cockpit rule, frozen exactly as it behaved before the cabin split.

    Deliberately has no SVX/EVN handling: the tag-based override never fired in
    practice, so the count threshold alone is what produced today's accepted
    output. ``flight`` is accepted for signature symmetry and is not read.
    """

    count = operating_cockpit_count(cockpit_crew_list)
    if count > HEAVY_COCKPIT_THRESHOLD:
        return True, f"effective cockpit count = {count} > {HEAVY_COCKPIT_THRESHOLD}"
    return False, f"effective cockpit count = {count} <= {HEAVY_COCKPIT_THRESHOLD}"


def classify_cabin_augmented_heavy(
    flight: CabinFlight,
    cabin_crew_list: Sequence[CabinCrewMember],
) -> tuple[bool, str]:
    """Return (is_heavy, reason). First matching rule wins."""

    # 1 & 2 — airport overrides, before anything is counted.
    airports = {
        code.strip().upper()
        for code in (flight.adep, flight.ades)
        if isinstance(code, str) and code.strip()
    }
    if SVX_AIRPORT in airports:
        return True, f"SVX override (ADEP={_show(flight.adep)}, ADES={_show(flight.ades)})"
    if EVN_AIRPORT in airports:
        return False, f"EVN override (ADEP={_show(flight.adep)}, ADES={_show(flight.ades)})"

    # 3 — exclusions.
    effective = _effective_cabin(cabin_crew_list)
    note = _function_gap_note(cabin_crew_list)

    # 4 — threshold.
    count = len(effective)
    if count > HEAVY_CABIN_THRESHOLD:
        return True, _join(f"effective cabin count = {count} > {HEAVY_CABIN_THRESHOLD}", note)

    # 5 — UNKNOWN pairing.
    if flight.is_unknown:
        heavy, pairing_reason = _resolve_unknown(flight, effective)
        return heavy, _join(f"UNKNOWN + {pairing_reason}", note)

    # 6 — otherwise.
    return False, _join(f"effective cabin count = {count} <= {HEAVY_CABIN_THRESHOLD}", note)


def effective_cabin_codes(
    cabin_crew_list: Sequence[CabinCrewMember],
) -> frozenset[str]:
    """The crew-set identity used to compare one leg against another."""

    return frozenset(
        member.crew_code.strip().upper()
        for member in _effective_cabin(cabin_crew_list)
        if member.crew_code and member.crew_code.strip()
    )


def _effective_cabin(
    cabin_crew_list: Sequence[CabinCrewMember],
) -> tuple[CabinCrewMember, ...]:
    return tuple(
        member
        for member in cabin_crew_list or ()
        if not _is_excluded_position(member)
        and not _is_confirmed_trainee(member)
    )


def _is_excluded_position(member: CabinCrewMember) -> bool:
    position = (member.position or "").strip().upper()
    return position in CABIN_EXCLUDED_POSITIONS


def _is_confirmed_trainee(member: CabinCrewMember) -> bool:
    """Only a *confirmed* trainee is excluded: Position SFA AND Function TRN.

    A missing Function is not evidence of anything, so it never excludes.
    """

    position = (member.position or "").strip().upper()
    function = (member.function or "").strip().upper() if member.function else None
    return position == TRAINEE_POSITION and function == TRAINEE_FUNCTION


def _function_gap_note(cabin_crew_list: Sequence[CabinCrewMember]) -> str | None:
    """Surface the blocked TRN exclusion instead of hiding it."""

    for member in cabin_crew_list or ():
        position = (member.position or "").strip().upper()
        if position == TRAINEE_POSITION and member.function is None:
            return FUNCTION_UNAVAILABLE_NOTE
    return None


def _resolve_unknown(
    flight: CabinFlight,
    effective: Sequence[CabinCrewMember],
) -> tuple[bool, str]:
    current_codes = effective_cabin_codes(effective)
    if flight.start_time_utc is None or flight.end_time_utc is None:
        return False, "flight times unavailable"
    if not flight.adjacent_legs:
        return False, "no adjacent leg"

    reason = "no qualifying adjacent leg"
    for leg in flight.adjacent_legs:
        if leg.start_time_utc is None or leg.end_time_utc is None:
            continue
        if leg.start_time_utc.date() != flight.start_time_utc.date():
            reason = "adjacent leg on a different UTC day"
            continue
        if effective_cabin_codes(leg.cabin_crew) != current_codes:
            reason = "adjacent leg has a different cabin crew set"
            continue
        gap = _break_between(flight, leg)
        if gap > UNKNOWN_MAX_BREAK:
            reason = f"break {_hours(gap)} > 4h"
            continue
        return True, (
            f"paired with adjacent leg, gap={_hours(gap)}, same crew, same UTC day"
        )
    return False, reason


def _break_between(flight: CabinFlight, leg: AdjacentLeg) -> timedelta:
    if leg.start_time_utc >= flight.end_time_utc:
        return leg.start_time_utc - flight.end_time_utc
    if leg.end_time_utc <= flight.start_time_utc:
        return flight.start_time_utc - leg.end_time_utc
    return timedelta(0)  # overlapping sectors leave no break


def _hours(delta: timedelta) -> str:
    return f"{delta.total_seconds() / 3600:.1f}h"


def _show(value: str | None) -> str:
    return (value or "—").strip().upper() or "—"


def _join(reason: str, note: str | None) -> str:
    return f"{reason}; {note}" if note else reason
