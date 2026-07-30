from typing import Protocol

from .schemas import CrewHoursRequest


class CrewHoursLeonClient(Protocol):
    """Future LEON boundary; S2 must not make network requests."""

    def fetch_crew_hours(self, request: CrewHoursRequest) -> None:
        ...


class PlaceholderCrewHoursLeonClient:
    def fetch_crew_hours(self, request: CrewHoursRequest) -> None:
        raise NotImplementedError("LEON integration is not implemented.")


def get_crew_hours_leon_client() -> CrewHoursLeonClient:
    return PlaceholderCrewHoursLeonClient()
