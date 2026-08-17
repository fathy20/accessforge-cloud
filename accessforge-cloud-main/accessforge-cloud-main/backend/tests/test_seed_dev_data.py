"""The dev seed tool: safety guard, idempotency, and the synthetic dataset."""

import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestSeedDevData(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def test_seeds_once_and_is_idempotent(self):
        from backend.tools.seed_dev_data import seed
        from backend.models import Job, Notification, Project, User

        self.assertEqual(seed(), 0)
        with self.app.database.SessionLocal() as session:
            self.assertEqual(session.query(User).count(), 4)
            self.assertEqual(session.query(Project).count(), 2)
            self.assertEqual(session.query(Job).count(), 3)
            self.assertEqual(session.query(Notification).count(), 2)

        # Second run changes nothing.
        self.assertEqual(seed(), 0)
        with self.app.database.SessionLocal() as session:
            self.assertEqual(session.query(User).count(), 4)

    def test_seeded_engineer_can_log_in_and_list_projects(self):
        from backend.tools.seed_dev_data import DEV_PASSWORD, seed

        self.assertEqual(seed(), 0)
        response = self.app.client.post(
            "/api/auth/login",
            json={"email": "dev-engineer@dev.local", "password": DEV_PASSWORD},
        )
        self.assertEqual(response.status_code, 200, response.text)
        headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
        projects = self.app.client.get("/api/projects", headers=headers)
        self.assertEqual(projects.status_code, 200)
        self.assertEqual(len(projects.json()), 2)

    def test_refuses_outside_a_local_sqlite_dev_database(self):
        import os

        from backend.tools.seed_dev_data import seed

        original = os.environ.get("APP_ENV")
        os.environ["APP_ENV"] = "production"
        try:
            self.assertEqual(seed(), 1)
        finally:
            if original is None:
                os.environ.pop("APP_ENV", None)
            else:
                os.environ["APP_ENV"] = original


if __name__ == "__main__":
    unittest.main()
