import re
from datetime import date
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from ...auth import get_current_user
from ...models import User
from .errors import (
    CrewHoursCapabilityError,
    LeonAuthenticationError,
    LeonConfigurationError,
    LeonContractError,
    LeonRateLimitError,
    LeonResponseError,
    LeonTimeoutError,
    LeonTransportError,
)
from .schemas import CrewHoursReportResponse, CrewHoursRequest, CrewHoursResponse
from .service import CrewHoursService, get_crew_hours_service

router = APIRouter(prefix="/crew-hours", tags=["crew-hours"])


def _validate_report_period(from_date: Optional[str], to_date: Optional[str]) -> str | None:
    parsed_dates: dict[str, date] = {}
    for parameter_name, value in (("from", from_date), ("to", to_date)):
        if value is None or value == "":
            continue
        if not isinstance(value, str) or not re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value
        ):
            return f"Query parameter '{parameter_name}' must be a valid YYYY-MM-DD date."
        try:
            parsed_dates[parameter_name] = date.fromisoformat(value)
        except ValueError:
            return f"Query parameter '{parameter_name}' must be a valid YYYY-MM-DD date."

    if "from" in parsed_dates and "to" in parsed_dates and parsed_dates["from"] > parsed_dates["to"]:
        return "Query parameter 'from' must not be after 'to'."
    return None


@router.get("/report", response_model=CrewHoursReportResponse, status_code=status.HTTP_200_OK)
def get_crew_hours_report(
    from_date: Annotated[Optional[str], Query(alias="from")] = None,
    to_date: Annotated[Optional[str], Query(alias="to")] = None,
    position: Annotated[Optional[str], Query()] = "All",
    crew_member: Annotated[Optional[str], Query()] = None,
    service: Annotated[CrewHoursService, Depends(get_crew_hours_service)] = None,
    current_user: User = Depends(get_current_user),
) -> CrewHoursReportResponse:
    """Fetch official flight and crew data grouped by crew member."""
    period_error = _validate_report_period(from_date, to_date)
    if period_error:
        raise HTTPException(status_code=422, detail=period_error)

    # Exception order is significant: LeonTimeoutError subclasses LeonTransportError,
    # and LeonRateLimitError subclasses LeonResponseError, so each must precede its parent.
    try:
        return service.get_crew_hours_report(
            from_date=from_date or "",
            to_date=to_date or "",
            position=position,
            crew_member=crew_member,
        )
    except CrewHoursCapabilityError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    except LeonTimeoutError:
        raise HTTPException(status_code=504, detail="LEON report request timed out.") from None
    except LeonRateLimitError as exc:
        headers = None
        if exc.retry_after_seconds is not None:
            headers = {"Retry-After": str(exc.retry_after_seconds)}
        raise HTTPException(
            status_code=429,
            detail="LEON report rate limit exceeded.",
            headers=headers,
        ) from None
    except LeonAuthenticationError:
        raise HTTPException(status_code=502, detail="LEON report authentication failed.") from None
    except LeonConfigurationError:
        raise HTTPException(status_code=503, detail="LEON official report is not configured.") from None
    except LeonTransportError:
        raise HTTPException(status_code=503, detail="LEON report transport failed.") from None
    except LeonContractError:
        raise HTTPException(status_code=502, detail="LEON report response was invalid.") from None
    except LeonResponseError:
        raise HTTPException(status_code=502, detail="LEON report response was invalid.") from None


@router.post("", response_model=CrewHoursResponse, status_code=status.HTTP_501_NOT_IMPLEMENTED)
def create_crew_hours_placeholder(
    request: CrewHoursRequest,
    service: Annotated[CrewHoursService, Depends(get_crew_hours_service)],
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Retain the legacy contract; tests assert its 401 and exact 501 body.

    The contract is pinned in test_crew_hours_skeleton.py, test_crew_hours_leon_foundation.py,
    and test_crew_hours_report_api.py; do not repurpose this route.
    """
    response = service.get_crew_hours(request)
    return JSONResponse(status_code=status.HTTP_501_NOT_IMPLEMENTED, content=response.model_dump())
