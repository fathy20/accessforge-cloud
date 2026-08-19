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
# Positioning slots (live values inside crew_position_names / flight-list
# position names): the member rides the flight but does not operate it.
# Excluded from operating counts and from STEP 4 crew-set comparison; their
# numeric block-time inclusion semantics are governed elsewhere and unchanged.
POSITIONING_POSITIONS = frozenset({"PSN", "PAD"})

# THE crew-set identity (owner ruling 2026-08-17): the ONE definition of
# "same crew" for comparisons — used by BOTH connected-duty grouping
# (domain.select_rows_for_period) and the STEP-4 rotation comparison
# (unknown_resolver.rotation_crew_codes). Do not create a third.
# Riders (PSN/PAD) and non-operating cockpit slots (OBS/OBS2/STB) never make
# two legs "different crews".
# NOTE: this is a SET IDENTITY only. Per-member block-time inclusion in the
# numeric totals (mcp_report aggregation; PSN-only exclusion, 2026-08-09
# parity ruling) is a separate settled rule and is untouched by this.
CREW_SET_EXCLUDED_POSITIONS = frozenset(
    POSITIONING_POSITIONS | frozenset({"OBS", "OBS2", "STB"})
)


def crew_set_identity(members) -> frozenset[str]:
    """Build the comparable crew set from (code, position) pairs."""

    codes = set()
    for code, position in members:
        if not isinstance(code, str) or not code.strip():
            continue
        normalized_position = (position or "").strip().upper()
        if normalized_position in CREW_SET_EXCLUDED_POSITIONS:
            continue
        codes.add(code.strip().upper())
    return frozenset(codes)
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

# The same two airports, in both code systems. Live data mixes them: the MCP
# report row's ``jl_adep/jl_ades_preferred_code`` and the flight-list context's
# ``_airport_code`` (ICAO preferred, IATA fallback) can name one airport two
# different ways on the same flight, and comparing against the IATA literal
# alone silently lost every ICAO-coded leg. Matching stays EXACT on either
# form after trim+uppercase — never a substring, so USSSX and UDYZA do not
# match. Adding a third airport to a rule means adding it here, once.
AIRPORT_CODE_ALIASES: Mapping[str, frozenset[str]] = {
    SVX_TAG: frozenset({"SVX", "USSS"}),
    EVN_TAG: frozenset({"EVN", "UDYZ"}),
}


def airport_code_forms(code: str) -> frozenset[str]:
    """Every accepted spelling of one airport, upper-cased."""

    normalized = code.strip().upper()
    return AIRPORT_CODE_ALIASES.get(normalized, frozenset({normalized}))

# --- Heavy Thresholds (strictly-greater) ---
# cockpit_count > HEAVY_COCKPIT_THRESHOLD → Heavy
# cabin_count   > HEAVY_CABIN_THRESHOLD   → Heavy
#
# Set to the operator's standard complement, so Heavy means "more than standard".
# Evidence, June 2026 Report Wizard, 304 flights carrying crew:
#   cockpit  2 crew ×289, 3 crew ×15, never more  → standard is 2
#   cabin    4 crew ×236, 5 ×14, 6 ×24, 7 ×6      → standard is 4
# The first agreed pair (cockpit 4 / cabin 2) was inverted against this: it
# marked 280 of 304 flights Heavy and the cockpit rule could never fire.
HEAVY_COCKPIT_THRESHOLD = 2
HEAVY_CABIN_THRESHOLD = 4

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
