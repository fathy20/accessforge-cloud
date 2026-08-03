import logging
from typing import Mapping, Protocol

logger = logging.getLogger(__name__)

from .config import get_leon_configuration, load_leon_configuration
from .errors import LeonConfigurationError, LeonContractError
from .flight_query import build_flight_list_query, parse_flight_list
from .graphql import LeonGraphQLExecutor
from .response_models import LeonFlight
from .token_provider import LeonAccessTokenProvider
from .transport import (
    BearerAccessTokenHeaderBuilder,
    HttpxLeonTransport,
    LeonAuthenticationHeaderBuilder,
    LeonRequest,
    LeonResponse,
    get_leon_authentication_header_builder,
)


class CrewHoursLeonClient(Protocol):
    def fetch_flights(self, from_date: str, to_date: str) -> list[LeonFlight]:
        ...


class LiveCrewHoursLeonClient:
    def __init__(self, executor: LeonGraphQLExecutor | None = None):
        self._executor = executor

    def _get_executor(self) -> LeonGraphQLExecutor:
        if self._executor is None:
            config = load_leon_configuration()
            transport = HttpxLeonTransport()
            token_provider = LeonAccessTokenProvider(config, transport)
            auth_header_builder = BearerAccessTokenHeaderBuilder()
            self._executor = LeonGraphQLExecutor(config, transport, token_provider, auth_header_builder)
        return self._executor

    def fetch_flights(self, from_date: str, to_date: str) -> list[LeonFlight]:
        query = build_flight_list_query(from_date, to_date)
        executor = self._get_executor()
        data = executor.execute_query(query)
        return parse_flight_list(data)


class MockCrewHoursLeonClient:
    def fetch_flights(self, from_date: str, to_date: str) -> list[LeonFlight]:
        # Demo data when LEON is not configured or in offline mode
        return [
            LeonFlight(
                flight_nid="FL-1001",
                start_time_utc=f"{from_date}T08:00:00Z",
                end_time_utc=f"{from_date}T11:30:00Z",
                flight_tags=[{"label": "SCHEDULED"}],
                start_airport={"code": {"icao": "HECA", "iata": "CAI"}},
                end_airport={"code": {"icao": "OEMA", "iata": "MED"}},
                aircraft={"registration": "SU-RSX", "acftType": {"icao": "B738", "iata": "738"}},
                crew_list=[
                    {
                        "contact": {"name": "Amr", "surname": "Hussien", "personCode": "CP101"},
                        "position": {"name": "CPT", "posType": "Cockpit"},
                        "flightTrainingType": None,
                    },
                    {
                        "contact": {"name": "Mohamed", "surname": "Ali", "personCode": "FO202"},
                        "position": {"name": "F/O", "posType": "Cockpit"},
                        "flightTrainingType": "TRN",
                    },
                ],
                journey_log={
                    "landingCount": 1,
                    "takeoffCrewLogin": {"code": "CP101"},
                    "landingCrewLogin": {"code": "CP101"},
                },
            ),
            LeonFlight(
                flight_nid="FL-1002",
                start_time_utc=f"{from_date}T13:00:00Z",
                end_time_utc=f"{from_date}T16:15:00Z",
                flight_tags=[{"label": "SCHEDULED"}],
                start_airport={"code": {"icao": "OEMA", "iata": "MED"}},
                end_airport={"code": {"icao": "HECA", "iata": "CAI"}},
                aircraft={"registration": "SU-RSX", "acftType": {"icao": "B738", "iata": "738"}},
                crew_list=[
                    {
                        "contact": {"name": "Amr", "surname": "Hussien", "personCode": "CP101"},
                        "position": {"name": "CPT", "posType": "Cockpit"},
                        "flightTrainingType": None,
                    },
                    {
                        "contact": {"name": "Mohamed", "surname": "Ali", "personCode": "FO202"},
                        "position": {"name": "F/O", "posType": "Cockpit"},
                        "flightTrainingType": None,
                    },
                ],
                journey_log={
                    "landingCount": 1,
                    "takeoffCrewLogin": {"code": "FO202"},
                    "landingCrewLogin": {"code": "FO202"},
                },
            ),
        ]


def get_crew_hours_leon_client() -> CrewHoursLeonClient:
    try:
        config = load_leon_configuration()
        return LiveCrewHoursLeonClient()
    except LeonConfigurationError as exc:
        logger.warning(f"LEON configuration not loaded ({exc}). Using mock client for demonstration.")
        return MockCrewHoursLeonClient()
