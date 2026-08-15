import unittest

from backend.copilot.service import CopilotService
from backend.copilot.wingman import WingmanApproval, WingmanMessage


class FakeWingmanClient:
    """Stands in for LEON's Wingman chat section."""

    def __init__(self, message_frames, approval=None):
        self._frames = list(message_frames)
        self._approval = approval
        self.started = []
        self.continued = []
        self.approvals = []

    def start_conversation(self, message, local_context=None):
        self.started.append((message, local_context))
        return "thread-1"

    def continue_conversation(self, thread_id, message, local_context=None):
        self.continued.append((thread_id, message, local_context))
        return thread_id

    def approval_status(self, thread_id):
        approval, self._approval = self._approval, None
        return approval

    def fetch_messages(self, thread_id):
        return self._frames.pop(0) if self._frames else ()

    def approve(self, thread_id, tool_names, *, approve=True, remember=False):
        self.approvals.append((thread_id, tuple(tool_names), approve, remember))


def _ai(text, status="COMPLETED", message_id="m1"):
    return WingmanMessage(
        message_id=message_id, text=text, sender="AI", status=status, created_at=None
    )


def _user(text):
    return WingmanMessage(
        message_id="u1", text=text, sender="USER", status="COMPLETED", created_at=None
    )


def _service(client, **kwargs):
    ticks = iter(range(0, 10_000))
    return CopilotService(
        client,
        sleep=lambda _seconds: None,
        monotonic=lambda: next(ticks),
        **kwargs,
    )


class TestCopilotService(unittest.TestCase):
    def test_polls_until_the_ai_message_settles(self):
        client = FakeWingmanClient([
            (_user("q"),),
            (_user("q"), _ai("Still working", status="PENDING")),
            (_user("q"), _ai("RSX431 is Heavy.")),
        ])

        answer = _service(client).ask("Is RSX431 heavy?")

        self.assertEqual(answer.text, "RSX431 is Heavy.")
        self.assertEqual(answer.thread_id, "thread-1")
        self.assertFalse(answer.approval_required)
        self.assertEqual(client.started, [("Is RSX431 heavy?", None)])

    def test_every_answer_carries_a_verifiable_source_line(self):
        client = FakeWingmanClient([(_ai("Answer.", message_id="msg-9"),)])

        answer = _service(client).ask("q")

        self.assertIsNotNone(answer.citation)
        self.assertEqual(
            answer.citation.source,
            "LEON Wingman · thread thread-1 · message msg-9",
        )

    def test_approval_request_is_surfaced_and_never_auto_approved(self):
        client = FakeWingmanClient(
            [(_ai("unused"),)],
            approval=WingmanApproval("thread-1", ("get-report-wizard-flight-scope-report",)),
        )

        answer = _service(client).ask("crew hours")

        self.assertTrue(answer.approval_required)
        self.assertEqual(
            answer.pending_tool_names, ["get-report-wizard-flight-scope-report"]
        )
        self.assertEqual(client.approvals, [], "service must not approve on its own")

    def test_declining_approval_returns_no_answer(self):
        client = FakeWingmanClient([])

        answer = _service(client).approve("thread-1", ["tool-a"], approve=False)

        self.assertIn("Declined", answer.text)
        self.assertEqual(client.approvals, [("thread-1", ("tool-a",), False, False)])

    def test_failed_status_is_reported_plainly(self):
        client = FakeWingmanClient([(_ai(None, status="FAILED"),)])

        answer = _service(client).ask("q")

        self.assertIn("failed", answer.text.lower())
        self.assertEqual(answer.citation.tone, "unresolved")

    def test_timeout_states_that_nothing_settled(self):
        client = FakeWingmanClient([(_ai("wait", status="PENDING"),)] * 50)

        answer = _service(client, poll_timeout_seconds=3).ask("q")

        self.assertIn("did not finish", answer.text)
        self.assertEqual(answer.thread_id, "thread-1")

    def test_thread_id_continues_an_existing_conversation(self):
        client = FakeWingmanClient([(_ai("Second answer."),)])

        answer = _service(client).ask("follow up", thread_id="thread-7", local_context="/crew")

        self.assertEqual(answer.text, "Second answer.")
        self.assertEqual(client.continued, [("thread-7", "follow up", "/crew")])
        self.assertEqual(client.started, [])


if __name__ == "__main__":
    unittest.main()
