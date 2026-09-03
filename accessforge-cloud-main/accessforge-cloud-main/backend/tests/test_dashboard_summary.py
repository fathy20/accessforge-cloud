"""GET /api/dashboard/summary aggregates in SQL; GET /api/jobs pages with offset.

The dashboard used to pull the caller's full job and upload lists and reduce
them in the browser. These tests pin the aggregate contract: per-status and
per-module counts, a 14-day UTC daily series, six-row recent lists, the shared
project count, and strict per-user scoping.
"""
import os
import shutil
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestDashboardSummary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="dashboard_summary_"))
        cls.original_cwd = os.getcwd()
        cls.original_db_url = os.environ.get("DATABASE_URL")
        cls.original_jwt_secret = os.environ.get("JWT_SECRET_KEY")
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.tmpdir / 'api.db'}"
        os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-with-at-least-thirty-two-bytes"
        os.chdir(cls.tmpdir)
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)

        import backend.database as database
        import backend.main as main
        from backend.auth import get_password_hash
        from backend.models import (
            AppRole,
            Job,
            JobStatus,
            Project,
            Upload,
            UploadKind,
            User,
            UserRole,
            UserStatus,
        )
        from backend.tools.sync_registry import sync_registry

        cls.database = database
        cls.main = main
        now = datetime.now(timezone.utc)
        with database.SessionLocal() as session:
            me = User(
                email="dash@example.com",
                hashed_password=get_password_hash("test-password"),
                full_name="Dash Owner",
                status=UserStatus.active,
            )
            other = User(
                email="other@example.com",
                hashed_password=get_password_hash("test-password"),
                full_name="Someone Else",
                status=UserStatus.active,
            )
            session.add_all([me, other])
            session.flush()
            session.add(UserRole(user_id=me.id, role=AppRole.engineer))
            session.add(UserRole(user_id=other.id, role=AppRole.engineer))
            sync_registry(session)

            def job(user, module_key, status, days_ago, hours=12):
                return Job(
                    user_id=user.id,
                    module_key=module_key,
                    status=status,
                    created_at=now - timedelta(days=days_ago, hours=hours),
                )

            session.add_all(
                [
                    # Inside the 14-day window.
                    job(me, "task_extractor", JobStatus.done, 0, hours=1),
                    job(me, "task_extractor", JobStatus.done, 1),
                    job(me, "task_extractor", JobStatus.failed, 1),
                    job(me, "cmp_tcm", JobStatus.running, 2),
                    job(me, "cmp_tcm", JobStatus.queued, 3),
                    job(me, "cover_merge", JobStatus.cancelled, 4),
                    # Outside the window: counted in totals, absent from daily.
                    job(me, "task_extractor", JobStatus.done, 20),
                    # Another user's job must never leak in.
                    job(other, "task_extractor", JobStatus.failed, 0, hours=2),
                ]
            )
            for index in range(7):
                session.add(
                    Upload(
                        user_id=me.id,
                        original_name=f"file-{index}.pdf",
                        storage_path=f"/tmp/file-{index}.pdf",
                        kind=UploadKind.pdf,
                        mime="application/pdf",
                        size_bytes=10,
                        sha256=f"{index:064x}",
                        created_at=now - timedelta(minutes=index),
                    )
                )
            session.add(
                Upload(
                    user_id=other.id,
                    original_name="theirs.pdf",
                    storage_path="/tmp/theirs.pdf",
                    kind=UploadKind.pdf,
                    mime="application/pdf",
                    size_bytes=10,
                    sha256="f" * 64,
                )
            )
            session.add_all(
                [
                    Project(owner_id=me.id, name="A320 C-check"),
                    Project(owner_id=other.id, name="B737 A-check"),
                ]
            )
            session.commit()

        cls.client = TestClient(main.app)
        auth = cls.client.post(
            "/api/auth/login",
            json={"email": "dash@example.com", "password": "test-password"},
        )
        auth.raise_for_status()
        cls.headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.database.engine.dispose()
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)
        os.chdir(cls.original_cwd)
        if cls.original_db_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = cls.original_db_url
        if cls.original_jwt_secret is None:
            os.environ.pop("JWT_SECRET_KEY", None)
        else:
            os.environ["JWT_SECRET_KEY"] = cls.original_jwt_secret
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_summary_requires_authentication(self):
        self.assertEqual(self.client.get("/api/dashboard/summary").status_code, 401)

    def test_summary_counts_are_scoped_to_the_caller(self):
        response = self.client.get("/api/dashboard/summary", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["jobs"]["total"], 7)
        self.assertEqual(
            body["jobs"]["by_status"],
            {"queued": 1, "running": 1, "done": 3, "failed": 1, "cancelled": 1},
        )
        self.assertTrue(body["jobs"]["active"])
        self.assertEqual(
            body["jobs"]["by_module"],
            [
                {"module_key": "task_extractor", "count": 4},
                {"module_key": "cmp_tcm", "count": 2},
                {"module_key": "cover_merge", "count": 1},
            ],
        )
        self.assertEqual(body["uploads"]["total"], 7)
        self.assertEqual(body["projects"]["total"], 2)

    def test_summary_daily_series_covers_fourteen_utc_days(self):
        body = self.client.get("/api/dashboard/summary", headers=self.headers).json()
        daily = body["jobs"]["daily"]
        self.assertEqual(len(daily), 14)

        today = datetime.now(timezone.utc).date()
        self.assertEqual(daily[0]["day"], (today - timedelta(days=13)).isoformat())
        self.assertEqual(daily[-1]["day"], today.isoformat())

        by_day = {row["day"]: row for row in daily}
        # Three done jobs exist, but the 20-day-old one sits outside the window
        # and is not bucketed; the other user's failed job today is not counted.
        self.assertEqual(sum(row["done"] for row in daily), 2)
        self.assertEqual(sum(row["failed"] for row in daily), 1)
        self.assertEqual(by_day[today.isoformat()]["failed"], 0)
        self.assertEqual(by_day[today.isoformat()]["done"], 1)

    def test_summary_recent_lists_are_capped_and_newest_first(self):
        body = self.client.get("/api/dashboard/summary", headers=self.headers).json()
        recent_jobs = body["jobs"]["recent"]
        recent_uploads = body["uploads"]["recent"]

        self.assertEqual(len(recent_jobs), 6)
        self.assertEqual(len(recent_uploads), 6)
        self.assertEqual(recent_uploads[0]["original_name"], "file-0.pdf")
        self.assertNotIn("theirs.pdf", [u["original_name"] for u in recent_uploads])
        created = [job["created_at"] for job in recent_jobs]
        self.assertEqual(created, sorted(created, reverse=True))
        # Serialised through the same explicit payload as /api/jobs.
        self.assertEqual(
            set(recent_jobs[0]),
            {
                "id", "module_key", "status", "progress", "error_message",
                "output_refs", "created_at", "started_at", "completed_at",
                "attempt", "cancel_requested",
            },
        )

    def test_jobs_list_pages_with_offset_and_reports_total(self):
        first = self.client.get("/api/jobs?limit=3", headers=self.headers)
        second = self.client.get("/api/jobs?limit=3&offset=3", headers=self.headers)
        tail = self.client.get("/api/jobs?limit=3&offset=6", headers=self.headers)

        self.assertEqual(first.headers["X-Total-Count"], "7")
        self.assertEqual(second.headers["X-Total-Count"], "7")
        self.assertEqual(len(first.json()), 3)
        self.assertEqual(len(second.json()), 3)
        self.assertEqual(len(tail.json()), 1)
        ids = [j["id"] for j in first.json() + second.json() + tail.json()]
        self.assertEqual(len(ids), len(set(ids)), "pages must not overlap")

        filtered = self.client.get("/api/jobs?status=done&limit=2", headers=self.headers)
        self.assertEqual(filtered.headers["X-Total-Count"], "3")
        self.assertEqual(len(filtered.json()), 2)


if __name__ == "__main__":
    unittest.main()
