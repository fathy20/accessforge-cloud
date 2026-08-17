import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from ..models import User
from ..rbac.permissions import require_permissions
from ..statistics.crew_hours.errors import (
    LeonAuthenticationError,
    LeonConfigurationError,
    LeonContractError,
    LeonRateLimitError,
    LeonResponseError,
    LeonTimeoutError,
    LeonTransportError,
)
from .schemas import CopilotAnswer, CopilotApproveRequest, CopilotAskRequest
from .service import CopilotService, build_report_fetcher, build_wingman_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/copilot", tags=["copilot"])


def get_copilot_service() -> CopilotService:
    # Construction reads LEON configuration; an unconfigured server must answer
    # with the same plain 503 as any other LEON failure, not an unhandled 500.
    try:
        return CopilotService(
            build_wingman_client(),
            fetch_report=build_report_fetcher(),
        )
    except Exception as exc:  # noqa: BLE001 - mapped to a plain client-facing status
        logger.warning("Copilot service construction failed (%s).", type(exc).__name__)
        raise _handle_leon_failure(exc) from exc


# Everything Copilot can reach — the grounded MCP report and the Wingman relay —
# is LEON crew data, so it is gated by the same grant as the Crew Hours module.
require_copilot_access = require_permissions("crew_hours.view")

ServiceDependency = Annotated[CopilotService, Depends(get_copilot_service)]
UserDependency = Annotated[User, Depends(require_copilot_access)]


def _handle_leon_failure(exc: Exception) -> HTTPException:
    """Map upstream failures to plain statements, never to a fabricated answer."""

    if isinstance(exc, LeonConfigurationError):
        return HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "LEON is not configured on this server, so Copilot cannot answer.",
        )
    if isinstance(exc, LeonAuthenticationError):
        return HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "LEON rejected this server's credentials. Copilot cannot answer.",
        )
    if isinstance(exc, LeonRateLimitError):
        return HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "LEON is rate limiting this server. Try again shortly.",
        )
    if isinstance(exc, LeonTimeoutError):
        return HTTPException(
            status.HTTP_504_GATEWAY_TIMEOUT, "LEON did not respond in time."
        )
    if isinstance(exc, (LeonTransportError, LeonResponseError, LeonContractError)):
        return HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"LEON Wingman is unavailable: {exc}"
        )
    return HTTPException(status.HTTP_502_BAD_GATEWAY, "LEON Wingman is unavailable.")


@router.post("/ask", response_model=CopilotAnswer)
def ask_copilot(
    payload: CopilotAskRequest,
    # Declaration order is resolution order: authorize before constructing
    # LEON clients, so anonymous requests never touch LEON configuration.
    current_user: UserDependency,
    service: ServiceDependency,
) -> CopilotAnswer:
    question = payload.question.strip()
    if not question:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "A question is required.")
    try:
        return service.ask(question, payload.thread_id, payload.local_context)
    except Exception as exc:  # noqa: BLE001 - mapped to a plain client-facing status
        logger.warning("Copilot ask failed (%s).", type(exc).__name__)
        raise _handle_leon_failure(exc) from exc


@router.post("/approve", response_model=CopilotAnswer)
def approve_copilot_tools(
    payload: CopilotApproveRequest,
    current_user: UserDependency,
    service: ServiceDependency,
) -> CopilotAnswer:
    try:
        return service.approve(
            payload.thread_id,
            payload.tool_names,
            approve=payload.approve,
            remember=payload.remember,
        )
    except Exception as exc:  # noqa: BLE001 - mapped to a plain client-facing status
        logger.warning("Copilot approval failed (%s).", type(exc).__name__)
        raise _handle_leon_failure(exc) from exc
