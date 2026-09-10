"""Turn a Wingman thread into one settled answer for the Copilot panel."""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Callable, Sequence

from ..statistics.crew_hours.config import get_leon_configuration
from ..statistics.crew_hours.domain import utc_today
from ..statistics.crew_hours.mcp_report import OfficialMcpReport, fetch_official_report
from ..statistics.crew_hours.token_provider import LeonAccessTokenProvider
from ..statistics.crew_hours.transport import HttpxLeonTransport
from .local_answers import answer_locally
from .schemas import CopilotAnswer, CopilotCitation, CopilotFact
from .wingman import WingmanApproval, WingmanChatClient, WingmanMessage

logger = logging.getLogger(__name__)

# Wingman answers asynchronously; the mutation only echoes the user's message.
# These bound how long a single HTTP request will wait for it to settle.
POLL_INTERVAL_SECONDS = 1.0
POLL_TIMEOUT_SECONDS = 45.0


def build_wingman_client() -> WingmanChatClient:
    configuration = get_leon_configuration()
    transport = HttpxLeonTransport()
    return WingmanChatClient(
        configuration,
        transport,
        LeonAccessTokenProvider(configuration, transport),
    )


def build_report_fetcher() -> Callable[[str, str], OfficialMcpReport]:
    """Report Wizard access over LEON's MCP host, independent of GraphQL."""

    configuration = get_leon_configuration()
    transport = HttpxLeonTransport()
    token_provider = LeonAccessTokenProvider(configuration, transport)

    def fetch(from_date: str, to_date: str) -> OfficialMcpReport:
        return fetch_official_report(
            configuration, transport, token_provider, from_date, to_date
        )

    return fetch


class CopilotService:
    def __init__(
        self,
        client: WingmanChatClient,
        *,
        fetch_report: Callable[[str, str], OfficialMcpReport] | None = None,
        today: Callable[[], date] = utc_today,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
        poll_timeout_seconds: float = POLL_TIMEOUT_SECONDS,
    ):
        self._client = client
        self._fetch_report = fetch_report
        self._today = today
        self._sleep = sleep
        self._monotonic = monotonic
        self._poll_timeout_seconds = poll_timeout_seconds

    def ask(
        self,
        question: str,
        thread_id: str | None = None,
        local_context: str | None = None,
    ) -> CopilotAnswer:
        # Roster and hours questions are answered from LEON's MCP report, which
        # is a different host from Wingman's GraphQL and stays up on its own.
        # A grounded answer citing real rows beats assistant prose, so it wins
        # when it applies. Only a follow-up in an existing thread skips it.
        if not thread_id and self._fetch_report is not None:
            grounded = self._try_local(question)
            if grounded is not None:
                return grounded

        if thread_id:
            resolved_thread = self._client.continue_conversation(
                thread_id, question, local_context
            )
        else:
            resolved_thread = self._client.start_conversation(question, local_context)
        return self._await_answer(resolved_thread)

    def _try_local(self, question: str) -> CopilotAnswer | None:
        """Never let a report failure block the Wingman path."""

        try:
            return answer_locally(
                question, today=self._today(), fetch_report=self._fetch_report
            )
        except Exception as exc:  # noqa: BLE001 - fall through to Wingman
            logger.warning(
                "Copilot local answer unavailable (%s); falling back to Wingman.",
                type(exc).__name__,
            )
            return None

    def approve(
        self,
        thread_id: str,
        tool_names: Sequence[str],
        *,
        approve: bool = True,
        remember: bool = False,
    ) -> CopilotAnswer:
        self._client.approve(thread_id, tool_names, approve=approve, remember=remember)
        if not approve:
            return CopilotAnswer(
                text="Declined. Wingman did not read that data, so there is no answer.",
                thread_id=thread_id,
            )
        return self._await_answer(thread_id)

    def _await_answer(self, thread_id: str) -> CopilotAnswer:
        """Poll until the newest AI message settles, or Wingman asks permission."""

        deadline = self._monotonic() + self._poll_timeout_seconds
        latest: WingmanMessage | None = None
        while True:
            approval = self._client.approval_status(thread_id)
            if approval is not None:
                return _approval_answer(approval)

            latest = _latest_ai_message(self._client.fetch_messages(thread_id))
            if latest is not None and latest.is_settled:
                return _settled_answer(thread_id, latest)

            if self._monotonic() >= deadline:
                logger.info(
                    "LEON Wingman thread did not settle within %.0fs (status=%s).",
                    self._poll_timeout_seconds,
                    latest.status if latest else "no-reply",
                )
                return CopilotAnswer(
                    text=(
                        "Wingman did not finish answering in time. The question was sent; "
                        "ask again to pick the thread back up."
                    ),
                    thread_id=thread_id,
                )
            self._sleep(POLL_INTERVAL_SECONDS)


def _latest_ai_message(
    messages: Sequence[WingmanMessage],
) -> WingmanMessage | None:
    for message in reversed(messages):
        if message.is_ai:
            return message
    return None


def _approval_answer(approval: WingmanApproval) -> CopilotAnswer:
    tools = ", ".join(approval.tool_names)
    return CopilotAnswer(
        text=(
            "Wingman needs permission to read LEON data before it can answer. "
            f"Requested tools: {tools}."
        ),
        thread_id=approval.thread_id,
        approval_required=True,
        pending_tool_names=list(approval.tool_names),
        citation=CopilotCitation(
            tone="unresolved",
            headline="Approval required",
            facts=[CopilotFact(label="Tools", value=tools, raw=True)],
            source=f"LEON Wingman · thread {approval.thread_id} · awaiting approval",
        ),
    )


def _settled_answer(thread_id: str, message: WingmanMessage) -> CopilotAnswer:
    status = (message.status or "").upper()
    if status in {"FAILED", "CANCELED"}:
        return CopilotAnswer(
            text=(
                "Wingman could not answer that. LEON reported the request as "
                f"{status.lower()}."
            ),
            thread_id=thread_id,
            citation=CopilotCitation(
                tone="unresolved",
                headline="Wingman did not answer",
                facts=[CopilotFact(label="Status", value=status, raw=True)],
                source=f"LEON Wingman · thread {thread_id} · {status}",
            ),
        )

    text = message.text or "Wingman returned an empty answer."
    return CopilotAnswer(
        text=text,
        thread_id=thread_id,
        # The source line attests provenance, not a specific row: this answer is
        # Wingman's own prose, produced inside the named LEON thread.
        citation=CopilotCitation(
            tone="resolved",
            headline="Answered by LEON Wingman",
            facts=[CopilotFact(label="Message", value=message.message_id or "—", raw=True)],
            source=f"LEON Wingman · thread {thread_id} · message {message.message_id or '—'}",
        ),
    )
