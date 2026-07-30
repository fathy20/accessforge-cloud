from typing import Mapping, Protocol

from .errors import LeonContractError
from .schemas import CrewHoursRequest
from .transport import LeonRequest, LeonResponse


class LeonAuthenticationHeaderBuilder(Protocol):
    def build(self, access_token: str) -> Mapping[str, str]:
        ...


class BearerAccessTokenHeaderBuilder:
    def build(self, access_token: str) -> Mapping[str, str]:
        return {"Authorization": f"Bearer {access_token}"}


def get_leon_authentication_header_builder() -> LeonAuthenticationHeaderBuilder:
    return BearerAccessTokenHeaderBuilder()


class CrewHoursLeonClient(Protocol):
    def send(self, request: LeonRequest) -> LeonResponse:
        ...

    def fetch_crew_hours(self, request: CrewHoursRequest) -> None:
        ...


class PlaceholderCrewHoursLeonClient:
    def send(self, request: LeonRequest) -> LeonResponse:
        raise LeonContractError("LEON client is not active for the Crew Hours skeleton.")

    def fetch_crew_hours(self, request: CrewHoursRequest) -> None:
        raise LeonContractError("Crew Hours operation is not implemented.")


def get_crew_hours_leon_client() -> CrewHoursLeonClient:
    """Keeps the S2 route independent from the S4 LEON integration foundation."""
    return PlaceholderCrewHoursLeonClient()
