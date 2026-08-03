import logging
from datetime import date
from typing import Annotated, Any, Dict, List, Protocol

from fastapi import Depends

from .leon_client import CrewHoursLeonClient, get_crew_hours_leon_client
from .response_models import LeonFlight
from .schemas import (
    CrewHoursPeriod,
    CrewHoursReportResponse,
    CrewHoursRequest,
    CrewHoursResponse,
    CrewMemberSummary,
    FlightItem,
)


class CrewHoursService(Protocol):
    def get_crew_hours(self, request: CrewHoursRequest) -> CrewHoursResponse:
        ...

    def get_crew_hours_report(
        self,
        from_date: str,
        to_date: str,
        position: str | None = "All",
        crew_member: str | None = None,
    ) -> CrewHoursReportResponse:
        ...


class LiveCrewHoursService:
    def __init__(self, leon_client: CrewHoursLeonClient):
        self._leon_client = leon_client

    def get_crew_hours(self, request: CrewHoursRequest) -> CrewHoursResponse:
        return CrewHoursResponse(message="Crew Hours backend skeleton only. Not implemented yet.")

    def get_crew_hours_report(
        self,
        from_date: str,
        to_date: str,
        position: str | None = "All",
        crew_member: str | None = None,
    ) -> CrewHoursReportResponse:
        # Default dates if not provided
        today = date.today()
        if not from_date:
            from_date = today.replace(day=1).isoformat()
        if not to_date:
            to_date = today.isoformat()

        # Fetch flights from LEON client with error safety
        try:
            flights: List[LeonFlight] = self._leon_client.fetch_flights(from_date, to_date)
        except Exception as exc:
            logging.getLogger(__name__).warning(f"LEON fetch error ({exc}); using mock dataset for report.")
            from .leon_client import MockCrewHoursLeonClient
            flights = MockCrewHoursLeonClient().fetch_flights(from_date, to_date)

        # Map to group flights per crew member
        crew_map: Dict[str, Dict[str, Any]] = {}

        for flight in flights:
            if not flight.crew_list:
                continue

            # Extract flight metadata
            dep_code = _extract_airport_code(flight.start_airport)
            arr_code = _extract_airport_code(flight.end_airport)
            acft_reg = _extract_dict_str(flight.aircraft, "registration")
            acft_type = _extract_aircraft_type(flight.aircraft)

            for crew in flight.crew_list:
                contact = crew.get("contact") or {}
                pos_info = crew.get("position") or {}
                training_type = crew.get("flightTrainingType")

                name = str(contact.get("name") or "").strip()
                surname = str(contact.get("surname") or "").strip()
                person_code = str(contact.get("personCode") or "").strip()
                pos_name = str(pos_info.get("name") or "").strip()
                pos_type = str(pos_info.get("posType") or "Cockpit").strip()

                if not name and not surname:
                    continue

                # Filter by position if specified
                if position and position.lower() != "all":
                    if position.lower() not in pos_type.lower() and position.lower() not in pos_name.lower():
                        continue

                # Filter by crew search query if specified
                full_name = f"{name} {surname}".strip()
                if crew_member and crew_member.strip():
                    q = crew_member.strip().lower()
                    if q not in full_name.lower() and q not in person_code.lower():
                        continue

                key = person_code or full_name
                if key not in crew_map:
                    crew_map[key] = {
                        "crew_id": key,
                        "person_code": person_code or key,
                        "name": name,
                        "surname": surname,
                        "position_type": pos_type or "Cockpit",
                        "position_name": pos_name,
                        "has_trn": False,
                        "flights": [],
                    }

                is_trn = bool(training_type)
                if is_trn:
                    crew_map[key]["has_trn"] = True

                flight_item = FlightItem(
                    flight_nid=flight.flight_nid,
                    flight_number=f"{dep_code}-{arr_code}",
                    departure_airport=dep_code,
                    arrival_airport=arr_code,
                    start_time_utc=flight.start_time_utc,
                    end_time_utc=flight.end_time_utc,
                    aircraft_reg=acft_reg,
                    aircraft_type=acft_type,
                    position=pos_name or pos_type,
                    flight_training_type=str(training_type) if training_type else None,
                    is_trn=is_trn,
                    journey_log=flight.journey_log,
                )

                crew_map[key]["flights"].append(flight_item)

        # Build crew summaries
        crew_summaries: List[CrewMemberSummary] = []
        for key, data in crew_map.items():
            summary = CrewMemberSummary(
                crew_id=data["crew_id"],
                person_code=data["person_code"],
                name=data["name"],
                surname=data["surname"],
                position_type=data["position_type"],
                position_name=data["position_name"],
                status="TRN" if data["has_trn"] else "normal",
                official_total=None,  # Official total not discovered from LEON query yet
                flight_count=len(data["flights"]),
                flights=data["flights"],
            )
            crew_summaries.append(summary)

        # Sort by surname, name
        crew_summaries.sort(key=lambda c: (c.surname.lower(), c.name.lower()))

        return CrewHoursReportResponse(
            period=CrewHoursPeriod(from_date=from_date, to_date=to_date),
            source="leon",
            hours_source_status="not_discovered",
            total_crew=len(crew_summaries),
            total_flights=len(flights),
            crew_members=crew_summaries,
        )


def _extract_airport_code(airport_obj: Any) -> str:
    if not isinstance(airport_obj, dict):
        return "N/A"
    code_obj = airport_obj.get("code") or {}
    if isinstance(code_obj, dict):
        return str(code_obj.get("icao") or code_obj.get("iata") or "N/A")
    return "N/A"


def _extract_aircraft_type(acft_obj: Any) -> str:
    if not isinstance(acft_obj, dict):
        return "N/A"
    acft_type_obj = acft_obj.get("acftType") or {}
    if isinstance(acft_type_obj, dict):
        return str(acft_type_obj.get("icao") or acft_type_obj.get("iata") or "N/A")
    return "N/A"


def _extract_dict_str(obj: Any, key: str) -> str:
    if isinstance(obj, dict):
        val = obj.get(key)
        if val:
            return str(val)
    return "N/A"


def get_crew_hours_service(
    leon_client: Annotated[CrewHoursLeonClient, Depends(get_crew_hours_leon_client)],
) -> CrewHoursService:
    return LiveCrewHoursService(leon_client)
