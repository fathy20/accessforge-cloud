import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, time, timedelta
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from openpyxl import load_workbook

_API_TEMP_DIR = Path(tempfile.mkdtemp(prefix="crew_hours_export_api_"))
_API_TEMP_DB = _API_TEMP_DIR / "api.db"
_original_database_url = os.environ.get("DATABASE_URL")
_original_jwt_secret = os.environ.get("JWT_SECRET_KEY")
os.environ["DATABASE_URL"] = f"sqlite:///{_API_TEMP_DB.as_posix()}"
os.environ["JWT_SECRET_KEY"] = _original_jwt_secret or "test-secret-key-for-ci-only-32-chars"
# Keep this API test deterministic: never load live LEON credentials during collection.
for _name in ("LEON_BASE_URL", "LEON_REFRESH_TOKEN", "LEON_MCP_URL", "LEON_TIMEOUT_SECONDS"):
    os.environ[_name] = ""

from backend.auth import get_current_user
from backend.main import CORS_ORIGINS, app
from backend.statistics.crew_hours.errors import LeonRateLimitError, LeonTimeoutError
from backend.statistics.crew_hours.export import DETAIL_HEADERS
from backend.statistics.crew_hours.router import (
    require_crew_hours_export,
    require_crew_hours_view,
)
from backend.statistics.crew_hours.schemas import (
    CrewHoursPeriod,
    CrewHoursReportResponse,
    CrewMemberSummary,
    FlightItem,
)
from backend.statistics.crew_hours.service import get_crew_hours_service

if _original_database_url is None:
    os.environ.pop("DATABASE_URL", None)
else:
    os.environ["DATABASE_URL"] = _original_database_url
if _original_jwt_secret is None:
    os.environ.pop("JWT_SECRET_KEY", None)
else:
    os.environ["JWT_SECRET_KEY"] = _original_jwt_secret


# The injected display name has no full_name twin, so the exporter falls back to
# it and the escaping path is genuinely exercised.
INJECTED_NAME = "=cmd|' /c calc'!A0"


def _flight(
    flight_nid: str,
    *,
    position: str,
    block_time: str,
    flight_number: str,
    journey_log: dict | None = None,
) -> FlightItem:
    return FlightItem(
        flight_nid=flight_nid,
        flight_number=flight_number,
        departure_airport="CAI",
        arrival_airport="HRG",
        start_time_utc="2026-06-03T06:00:00Z",
        end_time_utc="2026-06-03T07:15:00Z",
        aircraft_reg="SURSA",
        aircraft_type="A320",
        flight_date="2026-06-03",
        block_time=block_time,
        position=position,
        journey_log=journey_log,
    )


def _report() -> CrewHoursReportResponse:
    """Two Cockpit members (the first with two legs), one Cabin, two off-template."""

    return CrewHoursReportResponse(
        period=CrewHoursPeriod(from_date="2026-06-01", to_date="2026-06-30"),
        source="leon_mcp_report",
        hours_source_status="official_mcp_report",
        total_crew=5,
        total_flights=3,
        records_count=3,
        official_totals_available=2,
        official_totals_unavailable=2,
        official_totals_by_position={"Cockpit": "75:05", "Cabin": "01:30"},
        crew_members=[
            CrewMemberSummary(
                crew_id="INTERNAL-CREW-001",
                person_code="INTERNAL-CODE-001",
                display_name=INJECTED_NAME,
                full_name=None,
                position_type="Cockpit",
                official_total="75:05",
                flight_count=2,
                flights=[
                    _flight(
                        "INTERNAL-FLIGHT-001",
                        position="PAD",
                        block_time="01:30",
                        flight_number="RS101",
                        journey_log={"raw": "RAW LEON PAYLOAD"},
                    ),
                    _flight(
                        "INTERNAL-FLIGHT-002",
                        position="CPT",
                        block_time="01:30",
                        flight_number="RS102",
                    ),
                ],
            ),
            CrewMemberSummary(
                crew_id="TRAINING-CREW",
                person_code="TRAINING-CODE",
                display_name="Zaki Trainee",
                full_name="Zaki Trainee",
                position_type="Cockpit",
                status="TRN",
                official_total="TRN",
                raw_official_total="TRN",
                flight_count=0,
                flights=[],
            ),
            CrewMemberSummary(
                crew_id="INTERNAL-CREW-002",
                person_code="INTERNAL-CODE-002",
                display_name="Cabin Crew",
                full_name="Cabin Crew",
                position_type="Cabin",
                official_total=None,
                flight_count=1,
                flights=[
                    _flight(
                        "INTERNAL-FLIGHT-003",
                        position="FA1",
                        block_time="not-a-duration",
                        flight_number="RS103",
                    ),
                ],
            ),
            CrewMemberSummary(
                crew_id="INTERNAL-CREW-003",
                person_code="INTERNAL-CODE-003",
                display_name="Maintenance Crew",
                position_type="Maintenance",
                official_total="01:00",
                flight_count=0,
                flights=[],
            ),
            CrewMemberSummary(
                crew_id="INTERNAL-CREW-004",
                person_code="INTERNAL-CODE-004",
                display_name="Unclassified Crew",
                position_type=None,
                official_total="",
                flight_count=0,
                flights=[],
            ),
        ],
    )


class _RecordingReportService:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = 0
        self.arguments = []

    def get_crew_hours_report(self, **kwargs):
        self.calls += 1
        self.arguments.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class TestCrewHoursExport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def setUp(self):
        self.service = _RecordingReportService(result=_report())
        # The export route is gated by crew_hours.view + crew_hours.export;
        # this override represents a user who holds both grants.
        exporter = lambda: SimpleNamespace(email="exporter@example.com")  # noqa: E731
        app.dependency_overrides[require_crew_hours_export] = exporter
        app.dependency_overrides[require_crew_hours_view] = exporter
        app.dependency_overrides[get_crew_hours_service] = lambda: self.service

    def tearDown(self):
        app.dependency_overrides.pop(require_crew_hours_export, None)
        app.dependency_overrides.pop(require_crew_hours_view, None)
        app.dependency_overrides.pop(get_crew_hours_service, None)

    @classmethod
    def tearDownClass(cls):
        import backend.database as database

        database.engine.dispose()
        shutil.rmtree(_API_TEMP_DIR, ignore_errors=True)

    def _export_response(self, **params):
        query = {"from": "2026-06-01", "to": "2026-06-30", **params}
        return self.client.get("/api/statistics/crew-hours/report/export", params=query)

    def _workbook(self, response=None):
        response = response or self._export_response()
        self.assertEqual(response.status_code, 200)
        workbook = load_workbook(filename=io.BytesIO(response.content))
        self.addCleanup(workbook.close)
        return workbook

    # -- template shape ---------------------------------------------------

    def test_workbook_uses_the_manual_month_template(self):
        response = self._export_response()
        self.assertEqual(
            response.headers["content-type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        workbook = self._workbook(response)

        self.assertEqual(
            workbook.sheetnames,
            ["Cockpit", "Cockpit Summary", "Cabin", "Cabin Summary", "Report Information"],
        )
        self.assertEqual(
            DETAIL_HEADERS,
            (
                "Position type",
                "Name",
                "Surname",
                "Date",
                "Aircraft",
                "Flight number",
                "ADEP ",
                "ADES",
                "OFF",
                "ON",
                "Block time",
                "Heavy",
            ),
        )
        for sheet in ("Cockpit", "Cabin"):
            with self.subTest(sheet=sheet):
                header = tuple(
                    workbook[sheet].cell(row=4, column=column).value
                    for column in range(1, len(DETAIL_HEADERS) + 1)
                )
                self.assertEqual(header, DETAIL_HEADERS)

        summary = workbook["Cockpit Summary"]
        self.assertEqual(summary["B1"].value, "Cockpit HRS.Jun.26")
        self.assertEqual(summary["B2"].value, "Name")
        self.assertEqual(summary["D2"].value, "Block time")
        self.assertEqual(workbook["Cabin Summary"]["B1"].value, "Cabin HRS.Jun.26")

    def test_detail_blocks_repeat_headers_and_close_with_a_banded_total_row(self):
        workbook = self._workbook()
        cockpit = workbook["Cockpit"]

        # Block 1: header row 4, two legs, total row 7, then three blank rows.
        self.assertEqual(cockpit["A4"].value, "Position type")
        self.assertEqual(cockpit["F5"].value, "RS101")
        self.assertEqual(cockpit["F6"].value, "RS102")
        self.assertEqual(cockpit["A7"].value, "'=cmd|'")
        self.assertEqual(cockpit["I7"].value, "Total")
        self.assertEqual(cockpit["D7"].value, datetime(2026, 6, 1))
        self.assertEqual(cockpit["D7"].number_format, "mmm-yy")
        for blank in (8, 9, 10):
            self.assertIsNone(cockpit.cell(row=blank, column=1).value)

        # Block 2: the trainee has no legs, so header is immediately followed
        # by the total row.
        self.assertEqual(cockpit["A11"].value, "Position type")
        self.assertEqual(cockpit["A12"].value, "Zaki")
        self.assertEqual(cockpit["B12"].value, "Trainee")
        self.assertEqual(cockpit["I12"].value, "Total")

        # The banded row merges the date across D:H and "Total" across I:J,
        # exactly as the manual sheet does.
        merges = {str(m) for m in cockpit.merged_cells.ranges}
        self.assertIn("D7:H7", merges)
        self.assertIn("I7:J7", merges)

        cabin = workbook["Cabin"]
        self.assertEqual(cabin["B5"].value, "Cabin")
        self.assertEqual(cabin["C5"].value, "Crew")
        self.assertEqual(cabin["I6"].value, "Total")

    def test_position_type_column_marks_non_operating_legs(self):
        workbook = self._workbook()
        cockpit = workbook["Cockpit"]

        self.assertEqual(cockpit["A5"].value, "Not-Active")  # PAD leg
        self.assertEqual(cockpit["A6"].value, "Cockpit")  # operating leg

    def test_heavy_column_is_on_both_tabs_and_uses_the_sheet_vocabulary(self):
        report = _report()
        report.crew_members[0].flights[1].augmented_heavy = True
        report.crew_members[2].flights[0].augmented_heavy = True
        self.service.result = report

        workbook = self._workbook()
        self.assertEqual(workbook["Cockpit"]["L5"].value, "PAD")
        self.assertEqual(workbook["Cockpit"]["L6"].value, "Yes")
        # Cabin carries the Heavy verdict too, unlike the hand-made sheet.
        self.assertEqual(workbook["Cabin"]["L4"].value, "Heavy")
        self.assertEqual(workbook["Cabin"]["L5"].value, "Yes")

        for attribute, expected in (
            ({"augmented_heavy": False}, "No"),
            ({"is_trn": True}, "TRN"),
            ({}, "Unknown"),  # LEON left it unresolved; say so rather than guess
        ):
            with self.subTest(expected=expected):
                report = _report()
                for name, value in attribute.items():
                    setattr(report.crew_members[0].flights[1], name, value)
                self.service.result = report
                self.assertEqual(self._workbook()["Cockpit"]["L6"].value, expected)

    def test_heavy_verdict_follows_the_dashboard_and_prefers_the_duty_credit(self):
        """The screen shows duty_credit when it exists; so must the sheet."""

        report = _report()
        # The flight-level value and the member-duty allowance disagree — the
        # allowance is what CrewDetailFlightRow renders, so it wins here too.
        report.crew_members[0].flights[1].augmented_heavy = False
        report.crew_members[0].flights[1].duty_credit = True
        report.crew_members[0].flights[1].credit_source = "OPERATE_PLUS_RIDE"
        self.service.result = report

        self.assertEqual(self._workbook()["Cockpit"]["L6"].value, "Yes")

        report = _report()
        report.crew_members[0].flights[1].augmented_heavy = True
        report.crew_members[0].flights[1].duty_credit = False
        self.service.result = report

        self.assertEqual(self._workbook()["Cockpit"]["L6"].value, "No")

    def test_heavy_credit_count_matches_the_dashboard_badge(self):
        report = _report()
        report.crew_members[0].heavy_credits = 3
        report.crew_members[1].heavy_credits = 0
        self.service.result = report

        workbook = self._workbook()
        # Closing row of the member's block, under the Heavy column.
        self.assertEqual(workbook["Cockpit"]["L7"].value, "H.C 3")
        self.assertEqual(workbook["Cockpit"]["L12"].value, "H.C 0")

        summary = workbook["Cockpit Summary"]
        self.assertEqual(summary["E2"].value, "H.C")
        self.assertEqual(summary["E3"].value, 3)
        self.assertEqual(summary["E4"].value, 0)
        self.assertEqual(summary["E5"].value, 3)  # group total

    def test_leon_dd_mm_yyyy_log_dates_are_written_as_real_dates(self):
        """Live report rows carry DD-MM-YYYY; an ISO-only parser blanks the column."""

        report = _report()
        report.crew_members[0].flights[0].flight_date = "03-08-2026"
        self.service.result = report

        cell = self._workbook()["Cockpit"]["D5"]
        self.assertEqual(cell.value, datetime(2026, 8, 3))
        self.assertEqual(cell.number_format, "yyyy\\-mm\\-dd")

    def test_an_unreadable_date_is_kept_as_text_and_named_on_the_information_tab(self):
        report = _report()
        report.crew_members[0].flights[0].flight_date = "not-a-date"
        self.service.result = report

        workbook = self._workbook()
        self.assertEqual(workbook["Cockpit"]["D5"].value, "not-a-date")
        self.assertIn("not-a-date", workbook["Report Information"]["B10"].value)

    def test_a_leg_without_a_journey_log_keeps_its_row_with_empty_log_cells(self):
        """LEON leaves ADEP/ADES/OFF/ON/Block/Date empty when no log was filed."""

        report = _report()
        flight = report.crew_members[0].flights[0]
        flight.departure_airport = None
        flight.arrival_airport = None
        flight.start_time_utc = None
        flight.end_time_utc = None
        flight.block_time = None
        flight.flight_date = None
        self.service.result = report

        cockpit = self._workbook()["Cockpit"]
        # The row survives, identified by the flight-record fields.
        self.assertEqual(cockpit["F5"].value, "RS101")
        self.assertEqual(cockpit["E5"].value, "SURSA")
        for column in ("D5", "G5", "H5", "I5", "J5", "K5"):
            with self.subTest(cell=column):
                self.assertIsNone(cockpit[column].value)

    def test_totals_read_unavailable_when_leon_is_not_the_official_source(self):
        """hasOfficialMcpTotal gates the screen; the same gate applies here."""

        report = _report()
        report.hours_source_status = "not_discovered"
        self.service.result = report

        workbook = self._workbook()
        self.assertEqual(workbook["Cockpit"]["K7"].value, "Not available")
        self.assertEqual(workbook["Cockpit Summary"]["D3"].value, "Not available")

    # -- numbers ----------------------------------------------------------

    def test_official_totals_are_written_as_values_and_never_recomputed(self):
        workbook = self._workbook()

        # 75:05 is LEON's figure; the two legs sum to 3:00, so a recomputation
        # would be visible here.
        block_total = workbook["Cockpit"]["K7"]
        self.assertEqual(block_total.value, timedelta(hours=75, minutes=5))
        self.assertEqual(block_total.number_format, "[h]:mm")

        formulas = [
            cell.value
            for worksheet in workbook.worksheets
            for row in worksheet.iter_rows()
            for cell in row
            if cell.data_type == "f"
        ]
        self.assertEqual(formulas, [])

    def test_summary_lists_its_group_and_closes_with_a_grand_total(self):
        workbook = self._workbook()
        summary = workbook["Cockpit Summary"]

        self.assertEqual(summary["A3"].value, 1)
        self.assertEqual(summary["B3"].value, "'=cmd|'")
        self.assertEqual(summary["D3"].value, timedelta(hours=75, minutes=5))
        self.assertEqual(summary["D3"].number_format, "[h]:mm")

        self.assertEqual(summary["A4"].value, 2)
        self.assertEqual(summary["B4"].value, "Zaki")
        self.assertEqual(summary["C4"].value, "Trainee")
        self.assertEqual(summary["D4"].value, "TRN")
        self.assertEqual(summary["D4"].number_format, "General")

        self.assertEqual(summary["B5"].value, "Total")
        self.assertEqual(summary["D5"].value, timedelta(hours=75, minutes=5))
        self.assertEqual(summary["D5"].number_format, "[h]:mm")

        cabin_summary = workbook["Cabin Summary"]
        self.assertEqual(cabin_summary["D3"].value, "Not available")
        self.assertEqual(cabin_summary["D3"].number_format, "General")

    def test_leg_times_are_clock_values_and_block_time_is_a_duration(self):
        workbook = self._workbook()
        cockpit = workbook["Cockpit"]

        self.assertEqual(cockpit["D5"].value, datetime(2026, 6, 3))
        self.assertEqual(cockpit["D5"].number_format, "yyyy\\-mm\\-dd")
        self.assertEqual(cockpit["I5"].value, time(6, 0))
        self.assertEqual(cockpit["J5"].value, time(7, 15))
        self.assertEqual(cockpit["I5"].number_format, "h:mm")
        # A leg is under a day, so it carries the manual sheet's h:mm clock
        # format; only accumulating totals need the elapsed [h]:mm.
        self.assertEqual(cockpit["K5"].value, time(1, 30))
        self.assertEqual(cockpit["K5"].number_format, "h:mm")

        # An unparsable duration is preserved verbatim rather than guessed at.
        self.assertEqual(workbook["Cabin"]["K5"].value, "not-a-duration")

    # -- safety and provenance --------------------------------------------

    def test_formula_injection_is_escaped_and_unparsed_duration_is_reported(self):
        workbook = self._workbook()

        self.assertEqual(workbook["Cockpit"]["B5"].value, "'=cmd|'")
        self.assertEqual(workbook["Cockpit Summary"]["B3"].value, "'=cmd|'")

        information_values = [
            cell.value
            for row in workbook["Report Information"].iter_rows()
            for cell in row
            if cell.value is not None
        ]
        self.assertTrue(
            any(
                isinstance(value, str) and "not-a-duration" in value
                for value in information_values
            )
        )
        self.assertFalse(
            any(isinstance(value, str) and "TRN" in value for value in information_values)
        )

    def test_filename_is_named_after_the_month_and_is_safe(self):
        response = self._export_response(
            position="Cockpit;../secrets",
            crew_member=INJECTED_NAME,
        )
        disposition = response.headers["content-disposition"]
        filename = re.search(r'filename="([^"]+)"', disposition).group(1)

        self.assertEqual(disposition, 'attachment; filename="Jun-26-Hrs.xlsx"')
        self.assertRegex(filename, r"^[A-Za-z0-9._-]+$")
        self.assertNotIn("secrets", filename)
        self.assertNotIn("calc", filename)

    def test_filename_falls_back_to_the_range_when_the_period_spans_months(self):
        report = _report()
        report.period = CrewHoursPeriod(from_date="2026-06-01", to_date="2026-07-31")
        self.service.result = report

        response = self.client.get(
            "/api/statistics/crew-hours/report/export",
            params={"from": "2026-06-01", "to": "2026-07-31"},
        )

        self.assertEqual(
            response.headers["content-disposition"],
            'attachment; filename="crew-hours-2026-06-01-to-2026-07-31.xlsx"',
        )

    def test_report_information_records_period_timestamp_user_and_source(self):
        workbook = self._workbook()
        information = workbook["Report Information"]
        values = [
            cell.value
            for row in information.iter_rows()
            for cell in row
            if cell.value is not None
        ]

        self.assertIn("2026-06-01", values)
        self.assertIn("2026-06-30", values)
        self.assertIn("exporter@example.com", values)
        self.assertIn("LEON MCP", values)
        generated_at = information["B5"].value
        self.assertIsInstance(generated_at, str)
        self.assertRegex(generated_at, r"^2026-.*Z$")

    def test_maintenance_and_unclassified_crew_are_not_exported(self):
        workbook = self._workbook()
        workbook_text = "\n".join(
            str(cell.value)
            for worksheet in workbook.worksheets
            for row in worksheet.iter_rows()
            for cell in row
            if cell.value is not None
        )

        self.assertNotIn("Maintenance Crew", workbook_text)
        self.assertNotIn("Unclassified Crew", workbook_text)

    def test_forbidden_raw_payload_and_internal_identifiers_are_absent(self):
        workbook = self._workbook()
        workbook_text = "\n".join(
            str(cell.value)
            for worksheet in workbook.worksheets
            for row in worksheet.iter_rows()
            for cell in row
            if cell.value is not None
        )
        for forbidden in (
            "RAW LEON PAYLOAD",
            "INTERNAL-FLIGHT-001",
            "INTERNAL-CREW-001",
            "INTERNAL-CODE-001",
            "journey_log",
            "flight_nid",
            "crew_id",
            "person_code",
        ):
            self.assertNotIn(forbidden, workbook_text)

    # -- endpoint contract ------------------------------------------------

    def test_endpoint_requires_authentication(self):
        app.dependency_overrides.pop(require_crew_hours_export, None)
        app.dependency_overrides.pop(get_current_user, None)

        response = self._export_response()

        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.service.calls, 0)

    # The permissionless-user 403 contract is covered by AppHarness-backed
    # tests in test_endpoint_authorization.py: the grant check reads the
    # database, and this module's import-time app cannot guarantee one when
    # the whole suite runs interleaved with harness tests.

    def test_query_validation_matches_report_endpoint_and_skips_service(self):
        for query, expected_detail in (
            (
                {"from": "2026-13-01", "to": "2026-06-30"},
                "Query parameter 'from' must be a valid YYYY-MM-DD date.",
            ),
            (
                {"from": "2026-06-30", "to": "2026-06-01"},
                "Query parameter 'from' must not be after 'to'.",
            ),
        ):
            with self.subTest(query=query):
                response = self.client.get(
                    "/api/statistics/crew-hours/report/export",
                    params=query,
                )
                self.assertEqual(response.status_code, 422)
                self.assertEqual(response.json(), {"detail": expected_detail})
                self.assertEqual(self.service.calls, 0)

    def test_same_service_method_feeds_screen_and_export_without_live_leon(self):
        report_response = self.client.get(
            "/api/statistics/crew-hours/report",
            params={"from": "2026-06-01", "to": "2026-06-30", "position": "All"},
        )
        export_response = self._export_response(position="All")

        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(export_response.status_code, 200)
        self.assertEqual(self.service.calls, 2)
        self.assertEqual(self.service.arguments[0], self.service.arguments[1])
        self.assertEqual(self.service.arguments[0]["position"], "All")

    def test_content_disposition_is_exposed_to_allowed_browser_origin(self):
        response = self.client.get(
            "/api/statistics/crew-hours/report/export",
            params={"from": "2026-06-01", "to": "2026-06-30"},
            headers={"Origin": CORS_ORIGINS[0]},
        )

        self.assertEqual(response.status_code, 200)
        exposed_headers = {
            value.strip().lower()
            for value in response.headers["access-control-expose-headers"].split(",")
        }
        self.assertIn("content-disposition", exposed_headers)

    def test_leon_error_mapping_matches_report_endpoint(self):
        cases = (
            (LeonTimeoutError("timeout sentinel"), 504, "LEON report request timed out."),
            (LeonRateLimitError(17), 429, "LEON report rate limit exceeded."),
        )
        for error, expected_status, expected_detail in cases:
            with self.subTest(error=type(error).__name__):
                self.service = _RecordingReportService(error=error)
                app.dependency_overrides[get_crew_hours_service] = lambda: self.service
                response = self._export_response()
                self.assertEqual(response.status_code, expected_status)
                self.assertEqual(response.json(), {"detail": expected_detail})
                self.assertEqual(self.service.calls, 1)


if __name__ == "__main__":
    unittest.main()
