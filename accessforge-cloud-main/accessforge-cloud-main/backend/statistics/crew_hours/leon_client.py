from typing import Mapping, Protocol

from .augmented import AugmentedIndex, fetch_augmented_index
from .config import get_leon_configuration, load_leon_configuration
from .crew_context import CrewContextIndex, fetch_crew_context_index
from .errors import LeonContractError
from .flight_query import build_flight_list_query, parse_flight_list
from .graphql import LeonGraphQLExecutor
from .mcp_report import fetch_official_totals as fetch_official_mcp_totals
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

    def fetch_official_totals(self, from_date: str, to_date: str) -> dict[str, str]:
        ...

    def fetch_augmented_index(self, from_date: str, to_date: str) -> AugmentedIndex:
        ...

    def fetch_crew_context_index(self, from_date: str, to_date: str) -> CrewContextIndex:
        ...


class LiveCrewHoursLeonClient:
    def __init__(self, executor: LeonGraphQLExecutor | None = None):
        self._executor = executor
        self._configuration = None
        self._transport = None
        self._token_provider = None

    def _ensure_runtime(self) -> LeonGraphQLExecutor:
        if self._executor is None or self._token_provider is None:
            config = load_leon_configuration()
            transport = HttpxLeonTransport()
            token_provider = LeonAccessTokenProvider(config, transport)
            self._configuration = config
            self._transport = transport
            self._token_provider = token_provider
            self._executor = LeonGraphQLExecutor(
                config,
                transport,
                token_provider,
                BearerAccessTokenHeaderBuilder(),
            )
        return self._executor

    def fetch_flights(self, from_date: str, to_date: str) -> list[LeonFlight]:
        query = build_flight_list_query(from_date, to_date)
        return parse_flight_list(self._ensure_runtime().execute_query(query))

    def fetch_official_totals(self, from_date: str, to_date: str) -> dict[str, str]:
        self._ensure_runtime()
        return fetch_official_mcp_totals(
            self._configuration,
            self._transport,
            self._token_provider,
            from_date,
            to_date,
        )

    def fetch_augmented_index(self, from_date: str, to_date: str) -> AugmentedIndex:
        self._ensure_runtime()
        return fetch_augmented_index(
            self._configuration,
            self._transport,
            self._token_provider,
            from_date,
            to_date,
        )

    def fetch_crew_context_index(self, from_date: str, to_date: str) -> CrewContextIndex:
        self._ensure_runtime()
        return fetch_crew_context_index(
            self._configuration,
            self._transport,
            self._token_provider,
            from_date,
            to_date,
        )


def get_crew_hours_leon_client() -> CrewHoursLeonClient:
    """Construct lazily; live use still propagates configuration errors without demo data."""

    return LiveCrewHoursLeonClient()
