import re
from datetime import date, datetime
from typing import Mapping

from .errors import LeonContractError, LeonResponseError
from .response_models import LeonFlight


ISO_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# Cabin trainees are identified by their Work Schedule Function (SFA).  This
# selection is optional: callers drop it and retry when LEON rejects the field,
# so only this one line needs editing if the schema names it differently.
CREW_FUNCTION_SELECTION = "workSchedule { function }"


def build_flight_list_query(
    start: date | str,
    end: date | str,
    *,
    include_crew_function: bool = True,
) -> str:
    start_date = _coerce_date(start)
    end_date = _coerce_date(end)
    if start_date > end_date:
        raise LeonContractError("Flight query start date must not be after end date.")
    crew_function = f"\n      {CREW_FUNCTION_SELECTION}" if include_crew_function else ""
    return f'''query {{
  flightList(
    filter: {{
      timeInterval: {{ start: "{start_date.isoformat()}", end: "{end_date.isoformat()}" }}
      flightStatus: CONFIRMED
      isCnl: false
    }}
  ) {{
    flightNid
    startTimeUTC
    endTimeUTC
    flightTags {{ label }}
    startAirport {{ code {{ icao iata }} }}
    endAirport {{ code {{ icao iata }} }}
    acft {{ registration acftType {{ icao iata }} }}
    crewList {{
      contact {{ name surname personCode }}
      position {{ name posType }}
      flightTrainingType{crew_function}
    }}
    journeyLog {{
      takeoffCrewLogin {{ code }}
      landingCrewLogin {{ code }}
      pilotMonitoringLanding {{ code }}
      pilotMonitoringTakeOff {{ code }}
      landingCount
      approachList {{ approach count }}
      approachTypeList {{ approachType count }}
      autoland
    }}
  }}
}}'''


def parse_flight_list(data: Mapping[str, object]) -> list[LeonFlight]:
    flight_list = data.get("flightList")
    if not isinstance(flight_list, list):
        raise LeonResponseError("LEON GraphQL data did not contain a flightList array.")
    flights: list[LeonFlight] = []
    for item in flight_list:
        if not isinstance(item, dict):
            raise LeonResponseError("LEON flightList contained an invalid flight item.")
        flight_nid = item.get("flightNid")
        start_time_utc = item.get("startTimeUTC")
        end_time_utc = item.get("endTimeUTC")
        if not all(isinstance(value, str) and value for value in (flight_nid, start_time_utc, end_time_utc)):
            raise LeonResponseError("LEON flight item had invalid identity or time fields.")
        flights.append(LeonFlight(
            flight_nid=flight_nid,
            start_time_utc=start_time_utc,
            end_time_utc=end_time_utc,
            flight_tags=_optional_list(item.get("flightTags")),
            start_airport=_optional_object(item.get("startAirport")),
            end_airport=_optional_object(item.get("endAirport")),
            aircraft=_optional_object(item.get("acft")),
            crew_list=_optional_list(item.get("crewList")),
            journey_log=_optional_object(item.get("journeyLog")),
        ))
    return flights


def _coerce_date(value: date | str) -> date:
    if isinstance(value, datetime):
        raise LeonContractError("Flight query dates must not include a time component.")
    if type(value) is date:
        return value
    if not isinstance(value, str) or not ISO_DATE_PATTERN.fullmatch(value):
        raise LeonContractError("Flight query dates must use strict YYYY-MM-DD values.")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise LeonContractError("Flight query dates must be valid calendar dates.") from exc


def _optional_object(value: object) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LeonResponseError("LEON optional object field had an invalid shape.")
    return value


def _optional_list(value: object) -> list[Mapping[str, object]] | None:
    if value is None:
        return None
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise LeonResponseError("LEON optional list field had an invalid shape.")
    return value
