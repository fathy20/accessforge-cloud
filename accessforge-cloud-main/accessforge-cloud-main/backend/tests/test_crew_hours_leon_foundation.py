import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestLeonConfigurationFoundation(unittest.TestCase):
    base_url = "https://leon.invalid/api"
    refresh_token = "unit-test-refresh-token"

    def _load(self, values):
        from backend.statistics.crew_hours.config import load_leon_configuration
        with patch.dict(os.environ, values, clear=True):
            return load_leon_configuration()

    def test_refresh_token_contract_and_redacted_repr(self):
        from backend.statistics.crew_hours.errors import LeonConfigurationError

        with self.assertRaises(LeonConfigurationError):
            self._load({"LEON_BASE_URL": self.base_url, "LEON_API_KEY": "obsolete"})
        configuration = self._load({
            "LEON_BASE_URL": f"  {self.base_url}/  ",
            "LEON_REFRESH_TOKEN": f"  {self.refresh_token}  ",
        })
        self.assertEqual(configuration.base_url, self.base_url)
        self.assertEqual(configuration.refresh_token, self.refresh_token)
        self.assertNotIn(self.refresh_token, repr(configuration))


class TestCrewHoursEndpointCompatibility(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="crew_hours_leon_"))
        cls.original_db_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.tmpdir / 'skeleton.db'}"
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)
        import backend.main as main
        from backend.auth import get_current_user

        cls.main = main
        cls.get_current_user = get_current_user
        cls.client = TestClient(main.app)

    def setUp(self):
        self.main.app.dependency_overrides[type(self).get_current_user] = lambda: object()

    def tearDown(self):
        self.main.app.dependency_overrides.pop(type(self).get_current_user, None)

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

    def test_s2_endpoint_requires_authentication(self):
        self.main.app.dependency_overrides.pop(type(self).get_current_user, None)
        response = self.client.post("/api/statistics/crew-hours", json={})

        self.assertEqual(response.status_code, 401)

    def test_s2_endpoint_remains_exact_501(self):
        response = self.client.post("/api/statistics/crew-hours", json={})

        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json(), {
            "message": "Crew Hours backend skeleton only. Not implemented yet.",
        })


if __name__ == "__main__":
    unittest.main()
