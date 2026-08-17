"""DEPRECATED — the second Heavy engine, retired by the 2026-08-17 owner ruling.

Every surface now classifies Heavy through ``heavy.classify_flight_heavy``
(one engine; see docs/architecture/crew-hours-heavy-precedence-adr-2026-08-17.md
and MCP_Memory/development/decision-log.md). This module survives for one
release as thin wrappers so any out-of-tree caller fails loudly with a
DeprecationWarning instead of an ImportError, then it is deleted.

Contract changes versus the retired implementation, per the owner rulings:

  * EVN/SVX are FLIGHT-LEVEL absolutes — EVN now vetoes a cockpit-count Yes
    (``classify_cockpit_heavy`` previously had no EVN/SVX handling).
  * Cabin trainee = Work Schedule Function == "SFA" (never Position-only,
    and never Position SFA AND Function TRN).
  * PSN/PAD positioning slots never count as operating crew.
  * The SP/OPS cabin exclusion is removed (no approved cabin rule used it).
  * ``adjacent_legs``/``is_unknown`` are ignored: the pairing rule runs in
    the real engine over a full flight index, not over hand-carried legs.
  * Reasons are the engine's reason codes, not the old prose strings.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .crew_context import CrewContextEntry, CrewContextIndex, FlightContext
from .heavy import classify_flight_heavy
from .positions import CABIN_POS_TYPE, COCKPIT_POS_TYPE
from .unknown_resolver import build_rotation_index

# Airport codes, matched against ADEP/ADES — kept for import compatibility.
SVX_AIRPORT = "SVX"
EVN_AIRPORT = "EVN"


@dataclass(frozen=True)
class CabinCrewMember:
    crew_code: str | None = None
    position: str | None = None
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
    is_unknown: bool = False
    adjacent_legs: tuple[AdjacentLeg, ...] = ()


_DEPRECATION = (
    "backend.statistics.crew_hours.cabin_heavy is deprecated: call "
    "heavy.classify_flight_heavy instead (single Heavy engine, owner ruling "
    "2026-08-17). This module will be deleted next release."
)


def _single_flight_index(
    flight: CabinFlight, entries: tuple[CrewContextEntry, ...]
) -> CrewContextIndex:
    context = FlightContext(
        flight_nid=1,
        start_time_utc=flight.start_time_utc.isoformat() if flight.start_time_utc else None,
        end_time_utc=flight.end_time_utc.isoformat() if flight.end_time_utc else None,
        flight_tags=(),
        entries=entries,
        departure_airport=flight.adep,
        arrival_airport=flight.ades,
    )
    return CrewContextIndex(available=True, by_flight={1: entries}, contexts={1: context})


def _classify(flight: CabinFlight, entries: tuple[CrewContextEntry, ...]) -> tuple[bool, str]:
    index = _single_flight_index(flight, entries)
    verdict, reason = classify_flight_heavy(index, build_rotation_index(index), 1)
    return bool(verdict), reason


def classify_cockpit_heavy(
    flight: CabinFlight,
    cockpit_crew_list: Sequence[CrewContextEntry],
) -> tuple[bool, str]:
    """DEPRECATED wrapper. EVN/SVX now apply (they previously did not here)."""

    warnings.warn(_DEPRECATION, DeprecationWarning, stacklevel=2)
    entries = tuple(
        entry if entry.pos_type else CrewContextEntry(
            pos_type=COCKPIT_POS_TYPE,
            position=entry.position,
            training_type=entry.training_type,
            crew_code=entry.crew_code,
            crew_name=entry.crew_name,
            function=entry.function,
        )
        for entry in cockpit_crew_list
    )
    return _classify(flight, entries)


def classify_cabin_augmented_heavy(
    flight: CabinFlight,
    cabin_crew_list: Sequence[CabinCrewMember],
) -> tuple[bool, str]:
    """DEPRECATED wrapper. Trainee rule is Function == 'SFA'; no SP/OPS rule."""

    warnings.warn(_DEPRECATION, DeprecationWarning, stacklevel=2)
    entries = tuple(
        CrewContextEntry(
            pos_type=CABIN_POS_TYPE,
            position=member.position,
            training_type=None,
            crew_code=member.crew_code,
            function=member.function,
        )
        for member in cabin_crew_list or ()
    )
    return _classify(flight, entries)
