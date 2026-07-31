from pydantic import BaseModel


class CrewHoursRequest(BaseModel):
    """Placeholder request DTO; Crew Hours inputs are not defined in S2."""


class CrewHoursResponse(BaseModel):
    message: str
