"""LEON Wingman chat client.

RedSea Copilot does not run its own model.  It is a client of LEON's own
Wingman assistant, reached over the same GraphQL endpoint and the same
LEON_REFRESH_TOKEN the Crew Hours module already uses.

Shape of the upstream API, confirmed against the live schema:

  mutation wingmanAi.wingmanChat.startNewConversation(messageInput)
      -> returns ONLY the echoed user message plus a threadId.
  query    wingmanAi.wingmanChat.getMessagesForThread(threadId)
      -> the AI reply appears here, status PENDING until it settles.
  query    wingmanAi.wingmanChat.getThreadApprovalStatus(threadId)
      -> non-null when Wingman is waiting for permission to call an MCP tool.
  mutation wingmanAi.wingmanChat.approveMcpRequest(threadId, approvalInput)

Because the answer is not in the mutation response, callers poll
``fetch_messages`` until the newest AI message reaches COMPLETED.  LEON also
publishes the same result over a GraphQL subscription; polling is used here so
the module stays inside the existing synchronous HTTP transport.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, Sequence

from ..statistics.crew_hours.config import LeonConfiguration
from ..statistics.crew_hours.errors import LeonContractError, LeonResponseError
from ..statistics.crew_hours.graphql import LeonGraphQLExecutor
from ..statistics.crew_hours.token_provider import LeonAccessTokenProvider
from ..statistics.crew_hours.transport import (
    BearerAccessTokenHeaderBuilder,
    LeonHttpTransport,
)


# LEON wraps every union branch in a NonNull*Value envelope whose payload field
# is always literally named "value" -- but with a different type per branch.
# GraphQL rejects that as a field conflict, so every branch is aliased. Two
# rules learned from LEON's own validation errors, both easy to trip again:
#   1. alias each "value" whose sibling branch also selects "value";
#   2. declare variables non-null (!) -- the arguments are non-null, and a
#      nullable variable in a non-null position is a validation error.
_MESSAGE_RESULT_FRAGMENT = """
    ... on NonNullWingmanChatMessageResultUnionValue {
      result: value {
        ... on NonNullWingmanChatMessageResultValue {
          messageResult: value {
            threadId
            userMessage { messageId message sender status }
          }
        }
        ... on NonNullErrorListValue {
          errorValue: value { errorList { message category } }
        }
      }
    }
"""

_START_MUTATION = """
mutation($messageInput: WingmanChatThreadMessageInput!) {
  wingmanAi { wingmanChat { startNewConversation(messageInput: $messageInput) {
%s
    ... on WingmanChatSectionMutationTypeStartNewConversationViolationList {
      violations: value { message category path }
    }
  } } }
}""" % _MESSAGE_RESULT_FRAGMENT

_CONTINUE_MUTATION = """
mutation($threadId: WingmanChatThreadId!, $messageInput: WingmanChatThreadMessageInput!) {
  wingmanAi { wingmanChat { continueConversation(threadId: $threadId, messageInput: $messageInput) {
%s
    ... on WingmanChatSectionMutationTypeContinueConversationViolationList {
      violations: value { message category path }
    }
  } } }
}""" % _MESSAGE_RESULT_FRAGMENT

_MESSAGES_QUERY = """
query($threadId: WingmanChatThreadId!) {
  wingmanAi { wingmanChat { getMessagesForThread(threadId: $threadId) {
    ... on NonNullListOfNonNullWingmanChatMessageTypeValue {
      value { threadId messageId message sender status createdAt }
    }
    ... on ErrorList { errorList { message category } }
  } } }
}"""

_APPROVAL_QUERY = """
query($threadId: WingmanChatThreadId!) {
  wingmanAi { wingmanChat { getThreadApprovalStatus(threadId: $threadId) {
    threadId toolNames
  } } }
}"""

_APPROVE_MUTATION = """
mutation($threadId: WingmanChatThreadId!, $approvalInput: WingmanChatThreadRequestApprovalInput!) {
  wingmanAi { wingmanChat { approveMcpRequest(threadId: $threadId, approvalInput: $approvalInput) {
    ... on NonNullWingmanChatThreadIdValue { threadIdValue: value }
    ... on WingmanChatSectionMutationTypeApproveMcpRequestViolationList {
      violations: value { message category path }
    }
  } } }
}"""

_AVAILABILITY_QUERY = """
query { wingmanAi { wingmanChat { isAvailable settings { active } } } }
"""


class WingmanIdentityError(LeonResponseError):
    """The configured LEON credential cannot reach a per-user feature."""


@contextmanager
def _identity_guard() -> Iterator[None]:
    """Name the identity restriction instead of letting it read as an outage.

    Wingman chat is per-user: threads belong to a logged-in identity. LEON
    rejects an API-key credential for those resolvers, but only `loggedUser`
    says so plainly -- the chat resolvers throw a generic error instead. This
    turns that generic failure into the actionable one.
    """

    try:
        yield
    except LeonResponseError as exc:
        text = str(exc).lower()
        if "identity type" in text or "accessrestriction" in text:
            raise WingmanIdentityError(
                "LEON refused the configured credential for Wingman chat: it is an "
                "API key, and Wingman requires a user session, user access token, "
                "or personal API key. "
                f"LEON said: {exc}"
            ) from exc
        raise


@dataclass(frozen=True)
class WingmanMessage:
    message_id: str | None
    text: str | None
    sender: str | None
    status: str | None
    created_at: str | None

    @property
    def is_ai(self) -> bool:
        return (self.sender or "").upper() == "AI"

    @property
    def is_settled(self) -> bool:
        return (self.status or "").upper() in {"COMPLETED", "CANCELED", "FAILED"}


@dataclass(frozen=True)
class WingmanApproval:
    thread_id: str
    tool_names: tuple[str, ...]


class WingmanChatClient:
    """Read/write client for LEON's Wingman chat section."""

    def __init__(
        self,
        configuration: LeonConfiguration,
        transport: LeonHttpTransport,
        token_provider: LeonAccessTokenProvider,
    ):
        self._executor = LeonGraphQLExecutor(
            configuration,
            transport,
            token_provider,
            BearerAccessTokenHeaderBuilder(),
        )

    def is_available(self) -> bool:
        section = self._chat_section(self._executor.execute_query(_AVAILABILITY_QUERY))
        if section.get("isAvailable") is not True:
            return False
        settings = section.get("settings")
        # A null settings block means LEON never disabled it explicitly.
        if isinstance(settings, Mapping) and settings.get("active") is False:
            return False
        return True

    def start_conversation(self, message: str, local_context: str | None = None) -> str:
        with _identity_guard():
            payload = self._executor.execute_query(
                _START_MUTATION,
                {"messageInput": _message_input(message, local_context)},
            )
        return self._thread_id(payload, "startNewConversation")

    def continue_conversation(
        self,
        thread_id: str,
        message: str,
        local_context: str | None = None,
    ) -> str:
        with _identity_guard():
            payload = self._executor.execute_query(
                _CONTINUE_MUTATION,
                {
                    "threadId": thread_id,
                    "messageInput": _message_input(message, local_context),
                },
            )
        return self._thread_id(payload, "continueConversation")

    def fetch_messages(self, thread_id: str) -> tuple[WingmanMessage, ...]:
        section = self._chat_section(
            self._executor.execute_query(_MESSAGES_QUERY, {"threadId": thread_id})
        )
        node = section.get("getMessagesForThread")
        if not isinstance(node, Mapping):
            return ()
        _raise_for_error_list(node)
        rows = node.get("value")
        if rows is None:
            return ()
        if not isinstance(rows, list):
            raise LeonContractError("LEON Wingman returned an invalid message list.")
        return tuple(
            WingmanMessage(
                message_id=_optional_str(row.get("messageId")),
                text=_optional_str(row.get("message")),
                sender=_optional_str(row.get("sender")),
                status=_optional_str(row.get("status")),
                created_at=_optional_str(row.get("createdAt")),
            )
            for row in rows
            if isinstance(row, Mapping)
        )

    def approval_status(self, thread_id: str) -> WingmanApproval | None:
        section = self._chat_section(
            self._executor.execute_query(_APPROVAL_QUERY, {"threadId": thread_id})
        )
        node = section.get("getThreadApprovalStatus")
        if not isinstance(node, Mapping):
            return None
        tool_names = node.get("toolNames")
        names = tuple(
            name for name in (tool_names or []) if isinstance(name, str) and name.strip()
        )
        resolved_thread = _optional_str(node.get("threadId")) or thread_id
        if not names:
            return None
        return WingmanApproval(thread_id=resolved_thread, tool_names=names)

    def approve(
        self,
        thread_id: str,
        tool_names: Sequence[str],
        *,
        approve: bool = True,
        remember: bool = False,
    ) -> None:
        payload = self._executor.execute_query(
            _APPROVE_MUTATION,
            {
                "threadId": thread_id,
                "approvalInput": {
                    "toolNames": list(tool_names),
                    "approve": approve,
                    "remember": remember,
                },
            },
        )
        node = self._chat_section(payload).get("approveMcpRequest")
        if isinstance(node, Mapping):
            _raise_for_violations(node)

    # --- payload unwrapping -------------------------------------------------

    @staticmethod
    def _chat_section(payload: Mapping[str, Any]) -> Mapping[str, Any]:
        wingman = payload.get("wingmanAi")
        if not isinstance(wingman, Mapping):
            raise LeonResponseError("LEON response did not contain a wingmanAi object.")
        section = wingman.get("wingmanChat")
        if not isinstance(section, Mapping):
            raise LeonResponseError("LEON response did not contain a wingmanChat object.")
        return section

    def _thread_id(self, payload: Mapping[str, Any], field: str) -> str:
        node = self._chat_section(payload).get(field)
        if not isinstance(node, Mapping):
            raise LeonResponseError(f"LEON Wingman {field} returned no result.")
        _raise_for_violations(node)
        # Aliases mirror _MESSAGE_RESULT_FRAGMENT: result -> messageResult/errorValue.
        inner = node.get("result")
        if isinstance(inner, Mapping):
            _raise_for_error_list(inner)
            result = inner.get("messageResult")
            if isinstance(result, Mapping):
                thread_id = _optional_str(result.get("threadId"))
                if thread_id:
                    return thread_id
        raise LeonResponseError(f"LEON Wingman {field} did not return a thread id.")


def _message_input(message: str, local_context: str | None) -> dict[str, Any]:
    """Every field of WingmanChatThreadMessageInput is required.

    LEON declares localContext as String! and fileList as [FileDataInput!]!,
    so both must be sent even when empty -- omitting them is a 400, not a
    default.
    """

    return {
        "message": message,
        "localContext": local_context or "",
        "fileList": [],
    }


def _raise_for_violations(node: Mapping[str, Any]) -> None:
    """Violation lists carry {message, category, path} entries under `violations`."""

    values = node.get("violations")
    if not isinstance(values, list) or not values:
        return
    messages = [
        value.get("message")
        for value in values
        if isinstance(value, Mapping) and value.get("category") and value.get("message")
    ]
    if messages:
        raise LeonResponseError(f"LEON Wingman rejected the request: {'; '.join(messages)}")


def _raise_for_error_list(node: Mapping[str, Any]) -> None:
    """LEON's ErrorList wraps its entries in ``errorList``, not ``value``."""

    inner = node.get("errorValue")
    if not isinstance(inner, Mapping):
        return
    errors = inner.get("errorList")
    if not isinstance(errors, list) or not errors:
        return
    messages = [
        error.get("message")
        for error in errors
        if isinstance(error, Mapping) and error.get("message")
    ]
    if messages:
        raise LeonResponseError(f"LEON Wingman returned an error: {'; '.join(messages)}")


def _optional_str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None
