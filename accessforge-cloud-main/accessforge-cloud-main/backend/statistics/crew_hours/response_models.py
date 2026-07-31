from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LeonFlight:
    """Read-only LEON source record; S4 intentionally performs no Crew Hours calculations."""

    flight_nid: str
    start_time_utc: str
    end_time_utc: str
    flight_tags: list[Mapping[str, object]] | None
    start_airport: Mapping[str, object] | None
    end_airport: Mapping[str, object] | None
    aircraft: Mapping[str, object] | None
    crew_list: list[Mapping[str, object]] | None
    journey_log: Mapping[str, object] | None
