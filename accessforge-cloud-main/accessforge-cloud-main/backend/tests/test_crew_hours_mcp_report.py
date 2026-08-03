import json
import unittest
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.statistics.crew_hours.config import LeonConfiguration
from backend.statistics.crew_hours.errors import LeonContractError
from backend.statistics.crew_hours.leon_client import LeonFlight
from backend.statistics.crew_hours.mcp_report import fetch_official_totals
from backend.statistics.crew_hours.response_models import LeonFlight
from backend.statistics.crew_hours.service import LiveCrewHoursService
from backend.statistics.crew_hours.token_provider import LeonAccessTokenProvider
from backend.statistics.crew_hours.transport import FakeLeonTransport, LeonRawResponse


class TestMcpReport(unittest.TestCase):
    def _transport(self, report_rows):
        return FakeLeonTransport(responses=[
            LeonRawResponse(200, "t" * 72),
            LeonRawResponse(200, json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "result": {"protocolVersion": "2025-03-26"},
            })),
            LeonRawResponse(200, json.dumps({
                "jsonrpc": "2.0", "id": 2,
                "result": {"content": [{"type": "text", "text": json.dumps({"data": report_rows})}]},
            })),
        ])

    def test_fetches_and_aggregates_official_block_time_by_crew_code(self):
        transport = self._transport([
            {"crew_codes": ["AKA", "AHU"], "crew_names": ["Ahmed Kamel", "Amr Hussien"], "blockTimeJourneyLog": "01:30"},
            {"crew_codes": ["AKA"], "crew_names": ["Ahmed Kamel"], "blockTimeJourneyLog": "94:15"},
            {"crew_codes": ["AHU"], "crew_names": ["Amr Hussien"], "blockTimeJourneyLog": "84:15"},
        ])
        totals = fetch_official_totals(
            LeonConfiguration("https://rsx.leon.aero", "refresh-token", mcp_url="https://mcp.test.example/mcp"),
            transport,
            LeonAccessTokenProvider(LeonConfiguration("https://rsx.leon.aero", "refresh-token", mcp_url="https://mcp.test.example/mcp"), transport),
            "2026-06-01",
            "2026-06-30",
        )

        self.assertEqual(totals, {"AKA": "95:45", "AHU": "85:45"})
        self.assertEqual(len(transport.calls), 3)
        self.assertEqual(transport.calls[1].url, "https://mcp.test.example/mcp")
        self.assertEqual(transport.calls[2].json_body["method"], "tools/call")
        arguments = transport.calls[2].json_body["params"]["arguments"]
        self.assertEqual(arguments["dateFilter"]["start"], "2026-06-01T00:00:00Z")
        self.assertEqual(arguments["dateFilter"]["end"], "2026-06-30T23:59:59Z")
        self.assertEqual(arguments["columnList"], ["crew_codes", "crew_names", "blockTimeJourneyLog", "blockTimePlan"])
        self.assertEqual(transport.calls[0].form_field_names, ("refresh_token",))

    def test_invalid_block_time_is_rejected_without_secret_leakage(self):
        transport = self._transport([
            {"crew_codes": ["AKA"], "blockTimeJourneyLog": "not-a-duration"},
        ])
        provider = LeonAccessTokenProvider(
            LeonConfiguration("https://rsx.leon.aero", "refresh-token", mcp_url="https://mcp.test.example/mcp"),
            transport,
        )
        with self.assertRaises(LeonContractError) as raised:
            fetch_official_totals(
                LeonConfiguration("https://rsx.leon.aero", "refresh-token", mcp_url="https://mcp.test.example/mcp"),
                transport,
                provider,
                "2026-06-01",
                "2026-06-30",
            )
        self.assertNotIn("refresh-token", str(raised.exception))


class TestOfficialTotalsInService(unittest.TestCase):
    def test_official_total_is_exposed_without_manual_adjustment(self):
        class FakeCrewClient:
            def fetch_flights(self, from_date, to_date):
                return [LeonFlight(
                    flight_nid="FL-1",
                    start_time_utc="2026-06-01T08:00:00Z",
                    end_time_utc="2026-06-01T10:00:00Z",
                    flight_tags=None,
                    start_airport=None,
                    end_airport=None,
                    aircraft=None,
                    crew_list=[{"contact": {"name": "Ahmed", "surname": "Kamel", "personCode": "AKA"}, "position": {"name": "CPT", "posType": "Cockpit"}, "flightTrainingType": None}],
                    journey_log=None,
                )]

            def fetch_official_totals(self, from_date, to_date):
                return {"AKA": "95:45"}

        report = LiveCrewHoursService(FakeCrewClient()).get_crew_hours_report("2026-06-01", "2026-06-30")
        self.assertEqual(report.hours_source_status, "official_mcp_report")
        self.assertEqual(len(report.crew_members), 1)
        member = report.crew_members[0]
        self.assertEqual(member.official_total, "95:45")
        self.assertEqual(member.raw_official_total, "95:45")
        self.assertIsNone(member.reference_total)
        self.assertIsNone(member.variance_minutes)


if __name__ == "__main__":
    unittest.main()
