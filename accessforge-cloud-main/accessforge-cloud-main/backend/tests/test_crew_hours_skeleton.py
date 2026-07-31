import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestCrewHoursSkeleton(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="crew_hours_skeleton_"))
        cls.original_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.tmpdir / 'skeleton.db'}"
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)

        import backend.main as main

        cls.main = main
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.main.app.dependency_overrides.clear()
        cls.client.close()
        import backend.database as database
        database.engine.dispose()
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)
        if cls.original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.original_db_url
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_crew_hours_endpoint_returns_skeleton_response(self):
        response = self.client.post("/api/statistics/crew-hours", json={})

        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json(), {
            "message": "Crew Hours backend skeleton only. Not implemented yet.",
        })

    def test_crew_hours_service_dependency_can_be_overridden(self):
        from backend.statistics.crew_hours.router import get_crew_hours_service
        from backend.statistics.crew_hours.schemas import CrewHoursResponse

        class FakeCrewHoursService:
            calls = 0

            def get_crew_hours(self, request):
                self.calls += 1
                return CrewHoursResponse(message="Crew Hours backend skeleton only. Not implemented yet.")

        fake_service = FakeCrewHoursService()
        self.main.app.dependency_overrides[get_crew_hours_service] = lambda: fake_service
        try:
            response = self.client.post("/api/statistics/crew-hours", json={})
        finally:
            self.main.app.dependency_overrides.pop(get_crew_hours_service, None)

        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json(), {
            "message": "Crew Hours backend skeleton only. Not implemented yet.",
        })
        self.assertEqual(fake_service.calls, 1)


if __name__ == "__main__":
    unittest.main()
