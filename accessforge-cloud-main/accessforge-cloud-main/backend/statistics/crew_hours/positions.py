from typing import Mapping


# Derived from LEON's own role-slot column labels; see docs/architecture/leon-report-wizard-columns.md.
# Reconciled against live June 2026 data.
# PSN is non-operating for that member's numeric total.  PAD, FDP, FDPI, RMP,
# and INSP retain the approved existing inclusion semantics.
LEON_POSITION_GROUPS: Mapping[str, frozenset[str]] = {
    "Cockpit": frozenset(
        {
            "CPT",
            "CPT2",
            "CPT3",
            "CPT4",
            "CPT5",
            "FE",
            "FO",
            "FO2",
            "FO3",
            "FO4",
            "INS",
            "LTC",
            "LTE",
            "LTI",
            "OBS",
            "OBS2",
            "SP",
            "STB",
            "TRE",
            "TRI",
        }
    ),
    "Cabin": frozenset(
        {
            "EFA",
            "EFA2",
            "FA1",
            "FA2",
            "FA3",
            "FA4",
            "FA5",
            "FA6",
            "FA7",
            "FA8",
            "FA9",
            "FA10",
            "FA11",
            "FA12",
            "FA13",
            "FA14",
            "FA15",
            "IFA",
            "IFA2",
            "SFA",
            "SFA2",
            "SFA3",
        }
    ),
    "Maintenance": frozenset({"ENG1", "ENG2", "ENG3", "ENG4"}),
}

TRAINING_FLIGHT_TYPES = frozenset({"LINE_TRAINING", "LINE_CHECK"})
NON_OPERATING_COCKPIT_POSITIONS = frozenset({"OBS", "OBS2", "STB"})
COCKPIT_POS_TYPE = "COCKPIT"
CABIN_POS_TYPE = "CABIN"

# --- Training Detection ---
# Cockpit: OPS and SP positions are training crew — excluded from cockpit count.
TRAINING_POSITIONS_COCKPIT = frozenset({"OPS", "SP"})
# Cabin: SFA function (from WorkSchedule→Function) means cabin trainee — excluded from cabin count.
TRAINING_FUNCTION_CABIN = "SFA"

# --- Absolute flight tags ---
# EVN wins over every other rule (never Heavy); SVX forces Heavy.
EVN_TAG = "EVN"
SVX_TAG = "SVX"

# --- Heavy Thresholds (strictly-greater) ---
# cockpit_count > HEAVY_COCKPIT_THRESHOLD → Heavy
# cabin_count   > HEAVY_CABIN_THRESHOLD   → Heavy
HEAVY_COCKPIT_THRESHOLD = 4
HEAVY_CABIN_THRESHOLD = 2

# --- Minimum operating crew (existing, for reference) ---
# Evidence: fleet is 100% B738 and cockpit==2 was LEON-Normal in 718/718 flights.
DEFAULT_MINIMUM_COCKPIT = 2
MINIMUM_COCKPIT_BY_AIRCRAFT: Mapping[str, int] = {}
DEFAULT_MINIMUM_CABIN = 1
MINIMUM_CABIN_BY_AIRCRAFT: Mapping[str, int] = {}


def minimum_required_cockpit(aircraft_type: str | None) -> int:
    """Return the approved minimum cockpit crew for an aircraft type."""

    if not isinstance(aircraft_type, str) or not aircraft_type.strip():
        return DEFAULT_MINIMUM_COCKPIT
    leading_token = aircraft_type.strip().split(maxsplit=1)[0].casefold()
    for aircraft_key, minimum in MINIMUM_COCKPIT_BY_AIRCRAFT.items():
        key_token = aircraft_key.strip().split(maxsplit=1)[0].casefold()
        if key_token == leading_token:
            return minimum
    return DEFAULT_MINIMUM_COCKPIT


def minimum_required_cabin(aircraft_type: str | None) -> int:
    """Return the approved minimum cabin crew for an aircraft type."""

    if not isinstance(aircraft_type, str) or not aircraft_type.strip():
        return DEFAULT_MINIMUM_CABIN
    leading_token = aircraft_type.strip().split(maxsplit=1)[0].casefold()
    for aircraft_key, minimum in MINIMUM_CABIN_BY_AIRCRAFT.items():
        key_token = aircraft_key.strip().split(maxsplit=1)[0].casefold()
        if key_token == leading_token:
            return minimum
    return DEFAULT_MINIMUM_CABIN
