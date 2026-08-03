from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse

from .schemas import CrewHoursReportResponse, CrewHoursRequest, CrewHoursResponse
from .service import CrewHoursService, get_crew_hours_service

router = APIRouter(prefix="/crew-hours", tags=["crew-hours"])


@router.get("/report", response_model=CrewHoursReportResponse, status_code=status.HTTP_200_OK)
def get_crew_hours_report(
    from_date: Annotated[Optional[str], Query(alias="from")] = None,
    to_date: Annotated[Optional[str], Query(alias="to")] = None,
    position: Annotated[Optional[str], Query()] = "All",
    crew_member: Annotated[Optional[str], Query()] = None,
    service: Annotated[CrewHoursService, Depends(get_crew_hours_service)] = None,
) -> CrewHoursReportResponse:
    """Fetch official flight and crew data grouped by crew member."""
    return service.get_crew_hours_report(
        from_date=from_date or "",
        to_date=to_date or "",
        position=position,
        crew_member=crew_member,
    )


@router.post("", response_model=CrewHoursResponse, status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_crew_hours_placeholder(
    request: CrewHoursRequest,
    service: Annotated[CrewHoursService, Depends(get_crew_hours_service)],
) -> JSONResponse:
    response = service.get_crew_hours(request)
    return JSONResponse(status_code=status.HTTP_501_NOT_IMPLEMENTED, content=response.model_dump())
