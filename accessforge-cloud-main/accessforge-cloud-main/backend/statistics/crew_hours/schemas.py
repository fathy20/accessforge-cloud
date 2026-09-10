from typing import Any, Mapping
from pydantic import BaseModel, ConfigDict, Field


class CrewHoursPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: str = Field(..., alias="from")
    to_date: str = Field(..., alias="to")


class HeavyTraceStep(BaseModel):
    """One evaluated Heavy rule, as shown on the verdict cell of every leg.

    Mirrors ``statistics.crew_hours.trace.HeavyTraceStep``; the pure engine may
    not import pydantic, so the service layer converts at the boundary.
    """

    step: str
    outcome: str
    inputs: Mapping[str, Any] = Field(default_factory=dict)


class FdpShadow(BaseModel):
    """Regulatory FDP assessment of the duty this leg belongs to (shadow).

    Diagnostics only. Heavy is a Red Sea business/policy verdict decided by
    the owner's rulings, LEON's ``crewAugmentation`` and the precedence table;
    nothing in here is a Heavy verdict or an input to one.

    ``limit`` is the BASE Table A/B figure: the conditional differentials —
    the cabin +1:00 (OM 7.1-10 7-2-1), in-flight relief, split duty and
    commander's discretion — are not evaluated on this path, so it is not a
    final personal legal limit for the member it is shown beside.
    """

    tables_version: str
    table: str                       # "A" | "B"
    band: str                        # local start band, e.g. "15:00-21:59"
    sectors: int
    planned: str                     # H:MM
    limit: str | None                # H:MM; None when Table B has no row
    margin: str | None               # planned - limit, H:MM (negative = within)
    # planned > limit, and nothing more. NOT "this duty is Heavy" and not
    # "extra crew was required": see the retraction in fdp.py's docstring.
    needs_augmentation: bool | None
    # A False here is a diagnostic observation, not a defect: the verdict and
    # the shadow model answer different questions.
    agrees_with_verdict: bool | None # vs effective_heavy, when both are known
    # The member's crew group on this duty, as the roster's role slots name it.
    # Identity only: it never changes ``limit``.
    crew_group: str | None = None
    duty_leg_keys: list[str] = []


class FlightItem(BaseModel):
    flight_nid: str
    flight_number: str | None = None
    departure_airport: str | None = None
    arrival_airport: str | None = None
    start_time_utc: str | None = None
    end_time_utc: str | None = None
    aircraft_reg: str | None = None
    aircraft_type: str | None = None
    flight_date: str | None = None
    block_time: str | None = None
    position: str | None = None
    flight_training_type: str | None = None
    is_trn: bool = False
    journey_log: Mapping[str, Any] | None = None
    augmented_heavy: bool | None = None
    leon_heavy: bool | None = None
    derived_heavy: bool | None = None
    effective_heavy: bool | None = None
    heavy_source: str | None = None
    heavy_reason: str | None = None
    heavy_conflict: bool = False
    leon_augmentation: str | None = None
    # Trainee provenance: cockpit trainees come from the role slot (OPS/SP),
    # cabin trainees from the Work Schedule Function (SFA).
    is_training_position: bool = False
    is_training_function: bool = False
    # STEP 4 provenance for flights LEON left without an augmentation value.
    # unknown_resolved is the BADGE, and the badge means exactly one thing:
    # the rotation resolver established Heavy = True. A resolver No means "no
    # qualifying rotation found", which is not a local resolution and carries no
    # badge (owner ruling 2026-08-19). The reason is kept either way, because it
    # is diagnostic rather than a claim.
    unknown_resolved: bool = False
    unknown_resolution_reason: str | None = None
    # Every leg explains its own verdict, resolver-decided or not.
    heavy_trace: list[HeavyTraceStep] = []
    # SHADOW ONLY (2026-09-03): the regulatory FDP model measured on this
    # leg's duty. Never drives augmented_heavy/effective_heavy, the export, or
    # the credit — it is there to back-test the plan in
    # docs/architecture/heavy-fdp-regulatory-model-plan-2026-09-03.md.
    fdp_shadow: "FdpShadow | None" = None
    # Member-duty allowance (owner model 2026-08-20, validated 54/55 against
    # the manual July sheet): True when this leg belongs to a duty credited
    # for THIS member. None = allowance not computed (old fixtures).
    duty_credit: bool | None = None
    credit_source: str | None = None  # LEON_AUGMENTED | OPERATE_PLUS_RIDE


class CrewMemberSummary(BaseModel):
    crew_id: str
    person_code: str | None = None
    display_name: str
    full_name: str | None = None
    position_type: str | None = None
    position_name: str | None = None
    status: str = "normal"  # "normal" or "TRN"
    official_total: str | None = None
    raw_official_total: str | None = None
    reference_total: str | None = None
    variance_minutes: int | None = None
    flight_count: int = 0
    # H.C — how many of this member's duties earned a Heavy credit in the
    # requested window (the number the allowance sheet carries per member).
    heavy_credits: int = 0
    flights: list[FlightItem] = []


class CrewHoursReportResponse(BaseModel):
    period: CrewHoursPeriod
    source: str = "leon"
    hours_source_status: str = "not_discovered"
    total_crew: int = 0
    total_flights: int = 0  # Selected rows; records_count is every row LEON returned.
    records_count: int = 0
    official_totals_available: int = 0
    official_totals_unavailable: int = 0
    # Server-computed from integer minutes; clients must never recompute or re-sum these values.
    official_totals_by_position: dict[str, str] = {}
    # Join health across the three LEON sources (Report Wizard unique_id vs the
    # FTL trNid index and the flight-list flightNid index). "DEGRADED" is the
    # "IDs don't match" signature: a below-50% hit rate against a non-empty
    # index. It must be visible in the response, never only in a log.
    join_health: str = "OK"
    augmented_lookup_hits: int = 0
    augmented_lookup_attempts: int = 0
    crew_context_hits: int = 0
    crew_context_attempts: int = 0
    # "active" only when LEON supplied the Work Schedule Function field this
    # run; "unavailable" means the SFA-Function trainee exclusion did NOT fire
    # (LEON rejects the selection — known gap, owner ruling 2026-08-17), so
    # nobody should assume cabin trainees were excluded from operating counts.
    cabin_trainee_detection: str = "unavailable"
    crew_members: list[CrewMemberSummary] = []


class CrewHoursRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: str | None = Field(None, alias="from")
    to_date: str | None = Field(None, alias="to")
    position: str | None = "All"
    crew_member: str | None = None


class CrewHoursResponse(BaseModel):
    message: str
