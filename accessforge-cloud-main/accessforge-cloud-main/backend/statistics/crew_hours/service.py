from typing import Annotated, Protocol

from fastapi import Depends

from .leon_client import CrewHoursLeonClient, get_crew_hours_leon_client
from .schemas import CrewHoursRequest, CrewHoursResponse


SKELETON_MESSAGE = "Crew Hours backend skeleton only. Not implemented yet."


class CrewHoursService(Protocol):
    """Future Crew Hours application-service boundary."""

    def get_crew_hours(self, request: CrewHoursRequest) -> CrewHoursResponse:
        ...


class PlaceholderCrewHoursService:
    def __init__(self, leon_client: CrewHoursLeonClient):
        self._leon_client = leon_client

    def get_crew_hours(self, request: CrewHoursRequest) -> CrewHoursResponse:
        return CrewHoursResponse(message=SKELETON_MESSAGE)


def get_crew_hours_service(
    leon_client: Annotated[CrewHoursLeonClient, Depends(get_crew_hours_leon_client)],
) -> CrewHoursService:
    return PlaceholderCrewHoursService(leon_client)
