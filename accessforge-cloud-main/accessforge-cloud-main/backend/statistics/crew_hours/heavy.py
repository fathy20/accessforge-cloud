"""Pure Heavy decision and provenance engine.

The only side effect in this module is a warning log when an absolute tag
overrides a conflicting LEON value; every function is otherwise deterministic
and performs no I/O.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal, Sequence

from .crew_context import CrewContextEntry
from .positions import (
    CABIN_POS_TYPE,
    COCKPIT_POS_TYPE,
    EVN_TAG,
    HEAVY_CABIN_THRESHOLD,
    HEAVY_COCKPIT_THRESHOLD,
    NON_OPERATING_COCKPIT_POSITIONS,
    POSITIONING_POSITIONS,
    SVX_TAG,
    TRAINING_FLIGHT_TYPES,
    TRAINING_FUNCTION_CABIN,
    TRAINING_POSITIONS_COCKPIT,
)


logger = logging.getLogger(__name__)

HeavySource = Literal["LEON", "LOCAL_RULE", "LEON_AND_LOCAL", "UNKNOWN"]
HeavyReason = Literal[
    "LEON_AUGMENTED",
    "EVN_TAG",
    "SVX_TAG",
    "EVN_AIRPORT",
    "SVX_AIRPORT",
    "EXTRA_COCKPIT_CREW",
    "EXTRA_CABIN_CREW",
    "MULTIPLE_RULES",
    "NONE",
    "UNKNOWN",
]


# EVN and SVX are final on their own; they never fall through to the UNKNOWN
# resolver. The *_AIRPORT reasons are the live rule (route-based); the *_TAG
# reasons remain valid as the secondary signal.
ABSOLUTE_TAG_REASONS: frozenset[str] = frozenset(
    {"EVN_TAG", "SVX_TAG", "EVN_AIRPORT", "SVX_AIRPORT"}
)


@dataclass(frozen=True)
class HeavyDecision:
    leon_heavy: bool | None
    derived_heavy: bool | None
    effective_heavy: bool | None
    heavy_source: HeavySource
    heavy_reason: HeavyReason
    heavy_conflict: bool


def is_training_position(position: str | None) -> bool:
    """Cockpit trainees are identified by their LEON role slot (OPS/SP)."""

    normalized = _normalized(position)
    return normalized in {value.casefold() for value in TRAINING_POSITIONS_COCKPIT}


def is_training_function(function: str | None) -> bool:
    """Cabin trainees are identified by their Work Schedule Function (SFA)."""

    return _normalized(function) == TRAINING_FUNCTION_CABIN.casefold()


def _is_training_flight_type(training_type: str | None) -> bool:
    return _normalized(training_type) in {
        value.casefold() for value in TRAINING_FLIGHT_TYPES
    }


def _is_positioning_position(position: str | None) -> bool:
    """PSN/PAD ride the flight without operating it — never operating crew."""

    return _normalized(position) in {value.casefold() for value in POSITIONING_POSITIONS}


def operating_cockpit_count(entries: Sequence[CrewContextEntry]) -> int:
    """Count operating cockpit crew after the approved exclusions."""

    cockpit_type = COCKPIT_POS_TYPE.casefold()
    non_operating_positions = {
        value.casefold() for value in NON_OPERATING_COCKPIT_POSITIONS
    }
    return sum(
        1
        for entry in entries
        if _normalized(entry.pos_type) == cockpit_type
        and not _is_training_flight_type(entry.training_type)
        and not is_training_position(entry.position)
        and not _is_positioning_position(entry.position)
        and _normalized(entry.position) not in non_operating_positions
    )


def operating_cabin_count(entries: Sequence[CrewContextEntry]) -> int:
    """Count operating cabin crew after excluding Work-Schedule trainees."""

    cabin_type = CABIN_POS_TYPE.casefold()
    return sum(
        1
        for entry in entries
        if _normalized(entry.pos_type) == cabin_type
        and not _is_training_flight_type(entry.training_type)
        and not is_training_function(entry.function)
        and not _is_positioning_position(entry.position)
    )


def _normalized_tags(flight_tags: Sequence[str] | None) -> set[str] | None:
    if flight_tags is None:
        return None
    return {tag.strip().upper() for tag in flight_tags if isinstance(tag, str) and tag.strip()}


def is_evn_flight(flight_tags: Sequence[str] | None) -> bool:
    tags = _normalized_tags(flight_tags)
    return bool(tags) and EVN_TAG in tags


def is_svx_flight(flight_tags: Sequence[str] | None) -> bool:
    tags = _normalized_tags(flight_tags)
    return bool(tags) and SVX_TAG in tags


def _route_matches(route_airports: Sequence[str | None] | None, code: str) -> bool:
    """Exact airport-code match after trim+uppercase — never a substring match."""

    if not route_airports:
        return False
    target = code.strip().upper()
    return any(
        isinstance(airport, str) and airport.strip().upper() == target
        for airport in route_airports
    )


def derive_heavy_detail(
    entries: Sequence[CrewContextEntry] | None,
    aircraft_type: str | None,
    flight_tags: Sequence[str] | None = None,
    *,
    route_airports: Sequence[str | None] | None = None,
) -> tuple[bool | None, HeavyReason]:
    """Apply the approved local Heavy rules in their agreed precedence order.

    EVN and SVX are AIRPORT codes in live data (they appear in ADEP/ADES; LEON
    does not tag these flights — verified in the 2026-06 UI review against
    RSX331/RSX332 and RSX121/RSX122). ``route_airports`` carries every route
    code we know for the flight, from the report row and/or the flight-list
    context; a match on either source counts. Tags stay as a secondary signal.
    """

    # STEP 1 — EVN is an absolute exclusion and wins over every other rule,
    # including SVX. Airport first (the live rule), then the legacy tag.
    if _route_matches(route_airports, EVN_TAG):
        return False, "EVN_AIRPORT"
    if is_evn_flight(flight_tags):
        return False, "EVN_TAG"
    # STEP 2 — SVX is an absolute inclusion.
    if _route_matches(route_airports, SVX_TAG):
        return True, "SVX_AIRPORT"
    if is_svx_flight(flight_tags):
        return True, "SVX_TAG"

    # STEP 3 — operating counts, after the STEP 0 trainee exclusions.
    if entries is None or not entries:
        return None, "UNKNOWN"
    if operating_cockpit_count(entries) > HEAVY_COCKPIT_THRESHOLD:
        return True, "EXTRA_COCKPIT_CREW"
    if operating_cabin_count(entries) > HEAVY_CABIN_THRESHOLD:
        return True, "EXTRA_CABIN_CREW"
    return False, "NONE"


def derive_heavy(
    entries: Sequence[CrewContextEntry] | None,
    aircraft_type: str | None,
    flight_tags: Sequence[str] | None = None,
    *,
    route_airports: Sequence[str | None] | None = None,
) -> bool | None:
    """Return only the derived Heavy verdict; see derive_heavy_detail for its reason."""

    return derive_heavy_detail(
        entries, aircraft_type, flight_tags, route_airports=route_airports
    )[0]


def classify_flight_heavy(
    index,
    rotation_index,
    flight_nid: int | None,
    *,
    aircraft_type: str | None = None,
    leon_heavy: bool | None = None,
) -> tuple[bool | None, str]:
    """THE flight-level Heavy verdict — the single engine for every surface.

    Composes derive_heavy_detail → decide_heavy → resolve_unknown_heavy
    exactly as the Crew Hours report wires them, so the Copilot and any other
    caller can never disagree with the report (owner ruling, 2026-08-17).

    STEP 4 at flight level: the flight is Heavy when any operating member's
    rotation qualifies (positioning and non-operating slots never decide).
    Returns (verdict, reason); verdict None means "no crew context at all".
    """

    from .unknown_resolver import resolve_unknown_heavy, rotation_crew_codes

    context = (
        index.contexts.get(flight_nid)
        if index.available and flight_nid is not None
        else None
    )
    entries = context.entries if context is not None else ()
    derived, derived_reason = derive_heavy_detail(
        entries,
        aircraft_type,
        context.flight_tags if context is not None else None,
        route_airports=(
            (context.departure_airport, context.arrival_airport)
            if context is not None
            else None
        ),
    )
    decision = decide_heavy(leon_heavy, derived, derived_reason)
    if decision.effective_heavy is not None:
        return decision.effective_heavy, decision.heavy_reason
    # Rule 4: with LEON silent, an over-threshold operating count is final —
    # STEP 4 exists only for the case where the count rule returned UNKNOWN
    # (rule 5). decide_heavy deliberately leaves this None (its pinned table);
    # the flight-level finalization happens here.
    if decision.derived_heavy is True:
        return True, decision.heavy_reason

    codes = sorted(rotation_crew_codes(entries))
    if not codes:
        # No crew context at all is indeterminate; crew with no operating
        # member (all positioning/non-operating) is simply not Heavy.
        return (None, "UNKNOWN") if not entries else (False, "NONE")

    reason: str = "NO_FLIGHT_CONTEXT"
    for code in codes:
        resolution = resolve_unknown_heavy(index, rotation_index, flight_nid, code)
        if resolution.effective_heavy:
            return True, resolution.reason
        if reason == "NO_FLIGHT_CONTEXT":
            reason = resolution.reason
    return False, reason


def decide_heavy(
    leon_heavy: bool | None,
    derived_heavy: bool | None,
    derived_reason: HeavyReason | None = None,
) -> HeavyDecision:
    """Apply the product-owner precedence table exactly.

    Absolute tags come first: EVN forces No and SVX forces Yes, beating a
    conflicting LEON ``crewAugmentation`` value. Without a tag, the original
    LEON-first table is unchanged.
    """

    local_reason: HeavyReason = derived_reason or "EXTRA_COCKPIT_CREW"
    if derived_reason in ABSOLUTE_TAG_REASONS:
        # EVN → Heavy No, SVX → Heavy Yes; the verdict follows the airport/tag
        # rule, not whatever LEON said. A disagreeing LEON value is surfaced as
        # a conflict so the report never hides that the absolute rule won.
        tag_heavy = derived_reason in ("SVX_TAG", "SVX_AIRPORT")
        conflict = leon_heavy is not None and leon_heavy is not tag_heavy
        if conflict:
            logger.warning(
                "Absolute EVN/SVX rule %s overrode a conflicting LEON crewAugmentation value.",
                derived_reason,
            )
        return HeavyDecision(
            leon_heavy=leon_heavy,
            derived_heavy=derived_heavy,
            effective_heavy=tag_heavy,
            heavy_source="LOCAL_RULE",
            heavy_reason=local_reason,
            heavy_conflict=conflict,
        )
    if leon_heavy is True and derived_heavy is True:
        return HeavyDecision(
            leon_heavy=True,
            derived_heavy=True,
            effective_heavy=True,
            heavy_source="LEON_AND_LOCAL",
            heavy_reason="MULTIPLE_RULES",
            heavy_conflict=False,
        )
    if leon_heavy is True:
        return HeavyDecision(
            leon_heavy=True,
            derived_heavy=derived_heavy,
            effective_heavy=True,
            heavy_source="LEON",
            heavy_reason="LEON_AUGMENTED",
            heavy_conflict=False,
        )
    if leon_heavy is False and derived_heavy is True:
        return HeavyDecision(
            leon_heavy=False,
            derived_heavy=True,
            effective_heavy=False,
            heavy_source="LEON",
            heavy_reason=local_reason,
            heavy_conflict=True,
        )
    if leon_heavy is False:
        return HeavyDecision(
            leon_heavy=False,
            derived_heavy=derived_heavy,
            effective_heavy=False,
            heavy_source="LEON",
            heavy_reason="NONE",
            heavy_conflict=False,
        )
    # LEON is silent and no absolute tag applies (tags returned above, so
    # STEP 4 never runs for them): STEP 4 resolves this downstream.
    return HeavyDecision(
        leon_heavy=None,
        derived_heavy=derived_heavy,
        effective_heavy=None,
        heavy_source="UNKNOWN",
        heavy_reason=local_reason if derived_heavy else "UNKNOWN",
        heavy_conflict=False,
    )


def _normalized(value: str | None) -> str | None:
    return value.strip().casefold() if isinstance(value, str) else None
