import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient
from backend.main import app

class TestCrewHoursReportApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_get_crew_hours_report_endpoint(self):
        response = self.client.get("/api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30&position=Cockpit")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("period", data)
        self.assertIn("source", data)
        self.assertEqual(data["source"], "leon")
        self.assertIn("crew_members", data)
        self.assertIn("hours_source_status", data)
        self.assertEqual(data["hours_source_status"], "not_discovered")

if __name__ == "__main__":
    unittest.main()
