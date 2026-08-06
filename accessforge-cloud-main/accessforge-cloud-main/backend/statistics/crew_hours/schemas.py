from typing import Any, Mapping
from pydantic import BaseModel, ConfigDict, Field


class CrewHoursPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: str = Field(..., alias="from")
    to_date: str = Field(..., alias="to")


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
    crew_members: list[CrewMemberSummary] = []


class CrewHoursRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: str | None = Field(None, alias="from")
    to_date: str | None = Field(None, alias="to")
    position: str | None = "All"
    crew_member: str | None = None


class CrewHoursResponse(BaseModel):
    message: str
