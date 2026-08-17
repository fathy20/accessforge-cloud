"""Route-level authorization contracts for Copilot, Crew Hours, and Projects.

These are the regression tests for the audit finding that /api/copilot and
/api/statistics/crew-hours/report answered any authenticated session, and that
projects had no delete endpoint (the UI offered one) and no ownership rule.

Every LEON-backed service dependency is overridden with a local stub: this
developer machine carries live LEON credentials in backend/.env, so a test
that let the real factories run would talk to production LEON.
"""

import unittest

from backend.tests.test_rbac_permissions import AppHarness


class _StubCopilotService:
    """Answers without LEON; recording calls proves the gate was passed."""

    def __init__(self):
        self.calls = 0

    def ask(self, question, thread_id=None, local_context=None):
        from backend.copilot.schemas import CopilotAnswer

        self.calls += 1
        return CopilotAnswer(text="stub answer", thread_id="t-1")


class _StubReportService:
    def __init__(self):
        self.calls = 0

    def get_crew_hours_report(self, **kwargs):
        from backend.statistics.crew_hours.errors import LeonConfigurationError

        self.calls += 1
        # The router maps this to a plain 503; reaching it proves authorization
        # passed without this test ever touching a real LEON transport.
        raise LeonConfigurationError("stub: not configured")


class TestCopilotAuthorization(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        from backend.copilot.router import get_copilot_service

        self.service = _StubCopilotService()
        self.app.main.app.dependency_overrides[get_copilot_service] = lambda: self.service
        self._service_key = get_copilot_service

    def tearDown(self):
        self.app.main.app.dependency_overrides.pop(self._service_key, None)
        self.app.close()

    def test_unauthenticated_copilot_is_rejected(self):
        response = self.app.client.post("/api/copilot/ask", json={"question": "hi"})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.service.calls, 0)

    def test_permissionless_user_cannot_reach_copilot(self):
        # Copilot only serves LEON crew data; without crew_hours.view it must
        # be denied before the service is consulted.
        self.app.create_user("copilot-guest@example.test", roles=["guest"])
        response = self.app.client.post(
            "/api/copilot/ask",
            headers=self.app.headers("copilot-guest@example.test"),
            json={"question": "Who flew yesterday?"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Permission denied"})
        self.assertEqual(self.service.calls, 0)

    def test_viewer_passes_the_copilot_gate(self):
        # A viewer holds crew_hours.view, the grant Copilot is gated by.
        self.app.create_user("copilot-viewer@example.test", roles=["viewer"])
        response = self.app.client.post(
            "/api/copilot/ask",
            headers=self.app.headers("copilot-viewer@example.test"),
            json={"question": "Who flew yesterday?"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["text"], "stub answer")
        self.assertEqual(self.service.calls, 1)


class TestCrewHoursReportAuthorization(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        from backend.statistics.crew_hours.service import get_crew_hours_service

        self.service = _StubReportService()
        self.app.main.app.dependency_overrides[get_crew_hours_service] = lambda: self.service
        self._service_key = get_crew_hours_service

    def tearDown(self):
        self.app.main.app.dependency_overrides.pop(self._service_key, None)
        self.app.close()

    def _report(self, headers):
        return self.app.client.get(
            "/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30",
            headers=headers,
        )

    def _export(self, headers):
        return self.app.client.get(
            "/api/statistics/crew-hours/report/export?from=2026-06-01&to=2026-06-30",
            headers=headers,
        )

    def test_guest_cannot_read_the_crew_hours_report(self):
        self.app.create_user("report-guest@example.test", roles=["guest"])
        headers = self.app.headers("report-guest@example.test")

        self.assertEqual(self._report(headers).status_code, 403)
        self.assertEqual(self._export(headers).status_code, 403)
        self.assertEqual(self.service.calls, 0)

    def test_viewer_can_read_but_not_export(self):
        # viewer holds crew_hours.view but not crew_hours.export.
        self.app.create_user("report-viewer@example.test", roles=["viewer"])
        headers = self.app.headers("report-viewer@example.test")

        # Passing the view gate reaches the stub, which reports LEON as
        # unconfigured — mapped to 503, never 403.
        report = self._report(headers)
        self.assertEqual(report.status_code, 503)
        self.assertEqual(self.service.calls, 1)

        export = self._export(headers)
        self.assertEqual(export.status_code, 403)
        self.assertEqual(self.service.calls, 1)

    def test_engineer_passes_the_export_gate(self):
        self.app.create_user("report-engineer@example.test", roles=["engineer"])
        export = self._export(self.app.headers("report-engineer@example.test"))
        self.assertEqual(export.status_code, 503)
        self.assertEqual(self.service.calls, 1)


class TestProjectAuthorization(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def _create_project(self, email, name="Line Check A6"):
        response = self.app.client.post(
            "/api/projects",
            headers=self.app.headers(email),
            json={"name": name},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["id"]

    def test_owner_can_delete_own_project(self):
        self.app.create_user("proj-owner@example.test", roles=["engineer"])
        project_id = self._create_project("proj-owner@example.test")

        response = self.app.client.delete(
            f"/api/projects/{project_id}",
            headers=self.app.headers("proj-owner@example.test"),
        )
        self.assertEqual(response.status_code, 200)

        listing = self.app.client.get(
            "/api/projects", headers=self.app.headers("proj-owner@example.test")
        )
        self.assertEqual(listing.json(), [])

    def test_non_owner_cannot_delete_but_admin_can(self):
        self.app.create_user("proj-owner2@example.test", roles=["engineer"])
        self.app.create_user("proj-other@example.test", roles=["engineer"])
        self.app.create_user("proj-admin@example.test", roles=["admin"])
        project_id = self._create_project("proj-owner2@example.test")

        denied = self.app.client.delete(
            f"/api/projects/{project_id}",
            headers=self.app.headers("proj-other@example.test"),
        )
        self.assertEqual(denied.status_code, 403)

        allowed = self.app.client.delete(
            f"/api/projects/{project_id}",
            headers=self.app.headers("proj-admin@example.test"),
        )
        self.assertEqual(allowed.status_code, 200)

    def test_deleting_a_missing_project_is_a_404(self):
        self.app.create_user("proj-404@example.test", roles=["engineer"])
        response = self.app.client.delete(
            "/api/projects/does-not-exist",
            headers=self.app.headers("proj-404@example.test"),
        )
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
