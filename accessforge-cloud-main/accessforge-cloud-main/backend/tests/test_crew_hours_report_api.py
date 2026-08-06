import os
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
_API_TEMP_DIR = Path(tempfile.mkdtemp(prefix="crew_hours_api_"))
_API_TEMP_DB = _API_TEMP_DIR / "api.db"
_original_database_url = os.environ.get("DATABASE_URL")
_original_jwt_secret = os.environ.get("JWT_SECRET_KEY")
os.environ["DATABASE_URL"] = f"sqlite:///{_API_TEMP_DB.as_posix()}"
os.environ["JWT_SECRET_KEY"] = _original_jwt_secret or "test-secret-key-for-ci"
# Keep this API test deterministic: never load live LEON credentials during collection.
for _name in ("LEON_BASE_URL", "LEON_REFRESH_TOKEN", "LEON_MCP_URL", "LEON_TIMEOUT_SECONDS"):
    os.environ[_name] = ""

from backend.main import app
from backend.auth import get_current_user
from backend.statistics.crew_hours.errors import (
    CrewHoursCapabilityError,
    LeonAuthenticationError,
    LeonConfigurationError,
    LeonContractError,
    LeonRateLimitError,
    LeonResponseError,
    LeonTimeoutError,
    LeonTransportError,
)
from backend.statistics.crew_hours.mcp_report import OfficialMcpReport
from backend.statistics.crew_hours.router import _validate_report_period
from backend.statistics.crew_hours.service import LiveCrewHoursService, get_crew_hours_service


class _RaisingReportService:
    def __init__(self, error):
        self.error = error
        self.calls = 0

    def get_crew_hours_report(self, **kwargs):
        self.calls += 1
        raise self.error


class _RecordingReportService:
    def __init__(self):
        self.calls = 0

    def get_crew_hours_report(self, **kwargs):
        self.calls += 1
        raise AssertionError("The report service must not be called for invalid dates.")


_UPSTREAM_SENTINEL = (
    "CREW-CODE-SENTINEL CREW-NAME-SENTINEL TEST-TOKEN-SENTINEL "
    "Authorization: Bearer TEST-TOKEN-SENTINEL {\"raw\":\"payload-sentinel\"}"
)
if _original_database_url is None:
    os.environ.pop("DATABASE_URL", None)
else:
    os.environ["DATABASE_URL"] = _original_database_url
if _original_jwt_secret is None:
    os.environ.pop("JWT_SECRET_KEY", None)
else:
    os.environ["JWT_SECRET_KEY"] = _original_jwt_secret

class TestCrewHoursReportApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        app.dependency_overrides[get_current_user] = lambda: object()

    def tearDown(self):
        app.dependency_overrides.pop(get_current_user, None)

    @classmethod
    def tearDownClass(cls):
        import backend.database as database

        database.engine.dispose()
        shutil.rmtree(_API_TEMP_DIR, ignore_errors=True)

    def test_unauthenticated_crew_hours_endpoints_are_rejected(self):
        app.dependency_overrides.pop(get_current_user, None)

        report_response = self.client.get(
            "/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30&position=All"
        )
        create_response = self.client.post("/api/statistics/crew-hours", json={})

        self.assertEqual(report_response.status_code, 401)
        self.assertEqual(create_response.status_code, 401)

    def test_mcp_report_endpoint_returns_mcp_rows_without_graphql(self):
        class FakeCrewClient:
            def __init__(self):
                self.flight_calls = 0

            def fetch_flights(self, from_date, to_date):
                self.flight_calls += 1
                raise AssertionError("GraphQL flightList must not be required by the report")

            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"AKA": "95:45", "AHU": "85:45"},
                    [
                        {
                            "scope_row_unique_id": "leg-1",
                            "crew_codes": ["AKA", "AHU"],
                            "crew_names": ["Ahmed Kamel", "Amr Hussien"],
                            "crew_position_names": ["CPT", "FO"],
                            "blockTimeJourneyLog": "01:30",
                            "flightNo": "RS101",
                        },
                        {
                            "scope_row_unique_id": "leg-2",
                            "crew_codes": ["AKA"],
                            "crew_names": ["Ahmed Kamel"],
                            "crew_position_names": ["CPT"],
                            "blockTimeJourneyLog": "94:15",
                            "flightNo": "RS102",
                        },
                    ],
                )

        fake_client = FakeCrewClient()
        app.dependency_overrides[get_crew_hours_service] = lambda: LiveCrewHoursService(fake_client)
        try:
            response = self.client.get(
                "/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30&position=All"
            )
        finally:
            app.dependency_overrides.pop(get_crew_hours_service, None)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"], "leon_mcp_report")
        self.assertEqual(data["hours_source_status"], "official_mcp_report")
        self.assertEqual(data["total_crew"], 2)
        self.assertEqual(data["total_flights"], 2)
        self.assertEqual(data["records_count"], 2)
        self.assertEqual(data["official_totals_available"], 2)
        self.assertEqual(data["official_totals_unavailable"], 0)
        self.assertEqual(data["official_totals_by_position"], {"Cockpit": "181:30"})
        self.assertEqual(fake_client.flight_calls, 0)
        by_code = {member["person_code"]: member for member in data["crew_members"]}
        self.assertEqual(by_code["AKA"]["official_total"], "95:45")
        self.assertEqual(by_code["AHU"]["official_total"], "85:45")
        self.assertEqual(by_code["AKA"]["display_name"], "Ahmed Kamel")
        self.assertEqual(by_code["AKA"]["full_name"], "Ahmed Kamel")
        self.assertEqual(by_code["AKA"]["flights"][0]["flight_nid"], "leg-1")

    def test_empty_official_mcp_report_is_a_valid_200_response(self):
        class FakeCrewClient:
            def __init__(self):
                self.calls = 0

            def fetch_official_totals(self, from_date, to_date):
                self.calls += 1
                return OfficialMcpReport({}, [])

        fake_client = FakeCrewClient()
        app.dependency_overrides[get_crew_hours_service] = lambda: LiveCrewHoursService(fake_client)
        try:
            response = self.client.get(
                "/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30"
            )
        finally:
            app.dependency_overrides.pop(get_crew_hours_service, None)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["hours_source_status"], "official_mcp_report")
        self.assertEqual(data["crew_members"], [])
        self.assertEqual(data["total_crew"], 0)
        self.assertEqual(data["total_flights"], 0)
        self.assertEqual(data["records_count"], 0)
        self.assertEqual(data["official_totals_by_position"], {})
        self.assertEqual(fake_client.calls, 1)

    def test_invalid_report_dates_are_rejected_before_service_invocation(self):
        cases = (
            (
                "from=2026-13-01",
                "Query parameter 'from' must be a valid YYYY-MM-DD date.",
            ),
            (
                "from=not-a-date",
                "Query parameter 'from' must be a valid YYYY-MM-DD date.",
            ),
            (
                "from=2026-06-30&to=2026-06-01",
                "Query parameter 'from' must not be after 'to'.",
            ),
        )

        for query, expected_detail in cases:
            with self.subTest(query=query):
                fake_service = _RecordingReportService()
                app.dependency_overrides[get_crew_hours_service] = lambda: fake_service
                try:
                    response = self.client.get(f"/api/statistics/crew-hours/report?{query}")
                finally:
                    app.dependency_overrides.pop(get_crew_hours_service, None)

                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {"detail": expected_detail})
                self.assertEqual(fake_service.calls, 0)

    def test_report_period_helper_is_pure_and_preserves_empty_defaults(self):
        self.assertIsNone(_validate_report_period(None, ""))
        self.assertEqual(
            _validate_report_period("2026-02-30", "2026-03-01"),
            "Query parameter 'from' must be a valid YYYY-MM-DD date.",
        )
        self.assertEqual(
            _validate_report_period("2026-06-30", "2026-06-01"),
            "Query parameter 'from' must not be after 'to'.",
        )

    def test_unconfigured_report_does_not_use_demo_fallback(self):
        response = self.client.get(
            "/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30&position=All"
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"detail": "LEON official report is not configured."})

    def test_position_filter_reports_missing_mcp_capability(self):
        class FakeCrewClient:
            def fetch_official_totals(self, from_date, to_date):
                return OfficialMcpReport(
                    {"AKA": "01:00"},
                    [{"crew_codes": ["AKA"], "blockTimeJourneyLog": "01:00"}],
                )

        app.dependency_overrides[get_crew_hours_service] = lambda: LiveCrewHoursService(FakeCrewClient())
        try:
            response = self.client.get(
                "/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30&position=Cockpit"
            )
        finally:
            app.dependency_overrides.pop(get_crew_hours_service, None)

        self.assertEqual(response.status_code, 422)
        self.assertIn("position data", response.json()["detail"])

    def test_report_exception_status_map_is_ordered_and_value_free(self):
        cases = (
            (
                CrewHoursCapabilityError(
                    "LEON MCP report does not provide position data; remove the position filter."
                ),
                422,
                "LEON MCP report does not provide position data; remove the position filter.",
            ),
            (LeonAuthenticationError(_UPSTREAM_SENTINEL), 502, "LEON report authentication failed."),
            (LeonConfigurationError(_UPSTREAM_SENTINEL), 503, "LEON official report is not configured."),
            (LeonTransportError(_UPSTREAM_SENTINEL), 503, "LEON report transport failed."),
            (LeonContractError(_UPSTREAM_SENTINEL), 502, "LEON report response was invalid."),
            (LeonResponseError(_UPSTREAM_SENTINEL), 502, "LEON report response was invalid."),
            (LeonTimeoutError(_UPSTREAM_SENTINEL), 504, "LEON report request timed out."),
        )

        for exception, expected_status, expected_detail in cases:
            with self.subTest(exception=type(exception).__name__):
                fake_service = _RaisingReportService(exception)
                app.dependency_overrides[get_crew_hours_service] = lambda: fake_service
                try:
                    response = self.client.get(
                        "/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30"
                    )
                finally:
                    app.dependency_overrides.pop(get_crew_hours_service, None)

                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.json(), {"detail": expected_detail})
                self.assertNotIn(_UPSTREAM_SENTINEL, response.text)
                self.assertNotIn("Traceback", response.text)
                self.assertEqual(fake_service.calls, 1)

    def test_rate_limit_sets_retry_after_header(self):
        fake_service = _RaisingReportService(LeonRateLimitError(17))
        app.dependency_overrides[get_crew_hours_service] = lambda: fake_service
        try:
            response = self.client.get(
                "/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30"
            )
        finally:
            app.dependency_overrides.pop(get_crew_hours_service, None)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": "LEON report rate limit exceeded."})
        self.assertEqual(response.headers.get("Retry-After"), "17")

    def test_rate_limit_without_retry_after_omits_header(self):
        fake_service = _RaisingReportService(LeonRateLimitError(None))
        app.dependency_overrides[get_crew_hours_service] = lambda: fake_service
        try:
            response = self.client.get(
                "/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30"
            )
        finally:
            app.dependency_overrides.pop(get_crew_hours_service, None)

        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json(), {"detail": "LEON report rate limit exceeded."})
        self.assertNotIn("retry-after", response.headers)

    def test_legacy_post_contract_remains_authenticated_and_exact_501(self):
        response = self.client.post("/api/statistics/crew-hours", json={})

        self.assertEqual(response.status_code, 501)
        self.assertEqual(
            response.json(),
            {"message": "Crew Hours backend skeleton only. Not implemented yet."},
        )

    def test_official_parse_error_is_not_silently_reported_as_not_discovered(self):
        class FailingService:
            def get_crew_hours_report(self, **kwargs):
                raise LeonResponseError("LEON MCP report response did not contain report rows.")

        app.dependency_overrides[get_crew_hours_service] = lambda: FailingService()
        try:
            response = self.client.get("/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30")
        finally:
            app.dependency_overrides.pop(get_crew_hours_service, None)

        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json(), {"detail": "LEON report response was invalid."})
        self.assertNotEqual(response.status_code, 200)
        self.assertNotEqual(response.json().get("hours_source_status"), "not_discovered")

if __name__ == "__main__":
    unittest.main()
