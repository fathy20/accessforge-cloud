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


class TestStatisticsModuleRegistration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="statistics_modules_"))
        cls.original_db_url = os.environ.get("DATABASE_URL")
        cls.original_jwt_secret = os.environ.get("JWT_SECRET_KEY")
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.tmpdir / 'statistics.db'}"
        os.environ["JWT_SECRET_KEY"] = "statistics-module-test-secret-with-at-least-thirty-two-bytes"
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)

        import backend.database as database
        import backend.main as main

        cls.database = database
        cls.main = main
        cls.client_context = TestClient(main.app)
        cls.client = cls.client_context.__enter__()
        login = cls.client.post(
            "/api/auth/login",
            json={"email": "admin@redsea.com", "password": "password"},
        )
        login.raise_for_status()
        cls.headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)
        cls.database.engine.dispose()
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)
        if cls.original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.original_db_url
        if cls.original_jwt_secret is None:
            os.environ.pop("JWT_SECRET_KEY", None)
        else:
            os.environ["JWT_SECRET_KEY"] = cls.original_jwt_secret
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_public_and_admin_lists_register_crew_hours_once(self):
        expected_existing_keys = {
            "task_extractor", "task_stamping", "effectivity", "check_control",
            "utilization", "cmp_tcm", "cover_merge", "mail_merge",
        }
        public = self.client.get("/api/modules", headers=self.headers)
        public.raise_for_status()
        public_modules = public.json()
        public_crew_hours = [module for module in public_modules if module["key"] == "crew_hours"]
        self.assertEqual(public_crew_hours, [{
            "key": "crew_hours",
            "name": "Crew Hours",
            "enabled": True,
        }])
        self.assertEqual(len(public_modules), 9)
        self.assertTrue(expected_existing_keys.issubset({module["key"] for module in public_modules}))
        self.assertTrue(all(set(module) == {"key", "name", "enabled"} for module in public_modules))

        admin = self.client.get("/api/admin/modules", headers=self.headers)
        admin.raise_for_status()
        admin_modules = admin.json()
        admin_crew_hours = [module for module in admin_modules if module["key"] == "crew_hours"]
        self.assertEqual(admin_crew_hours, [{
            "id": "mod-9",
            "key": "crew_hours",
            "name": "Crew Hours",
            "category": "Statistics",
            "enabled": True,
        }])
        self.assertEqual(len(admin_modules), 9)
        self.assertTrue(expected_existing_keys.issubset({module["key"] for module in admin_modules}))

    def test_startup_seed_is_idempotent_for_crew_hours(self):
        from backend.models import Module

        with self.database.SessionLocal() as session:
            self.assertEqual(session.query(Module).count(), 9)
            self.assertEqual(session.query(Module).filter(Module.key == "crew_hours").count(), 1)

        self.main.startup_db_seed()

        with self.database.SessionLocal() as session:
            crew_hours = session.query(Module).filter(Module.key == "crew_hours").all()
            self.assertEqual(session.query(Module).count(), 9)
            self.assertEqual(len(crew_hours), 1)
            self.assertEqual(crew_hours[0].name, "Crew Hours")
            self.assertEqual(crew_hours[0].category, "Statistics")
            self.assertTrue(crew_hours[0].enabled)


if __name__ == "__main__":
    unittest.main()
