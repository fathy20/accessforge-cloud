from typing import Annotated

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from .schemas import CrewHoursRequest, CrewHoursResponse
from .service import CrewHoursService, get_crew_hours_service


router = APIRouter(prefix="/crew-hours", tags=["crew-hours"])


@router.post("", response_model=CrewHoursResponse, status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_crew_hours_placeholder(
    request: CrewHoursRequest,
    service: Annotated[CrewHoursService, Depends(get_crew_hours_service)],
) -> JSONResponse:
    response = service.get_crew_hours(request)
    return JSONResponse(status_code=status.HTTP_501_NOT_IMPLEMENTED, content=response.model_dump())
