"""Durable job execution: atomic claim, lease fencing, stale reclaim, the
worker's supervision loop (cancel / timeout / crash), and the cancel and retry
endpoints. Runs on SQLite; SQL Server contention behaviour is documented as
untested here (see docs/deploy/docker.md).
"""
import os
import shutil
import sys
import tempfile
import time
import unittest
from datetime import timedelta
from pathlib import Path

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# A child that never finishes on its own: the supervisor must kill it.
SLEEPING_CHILD = [sys.executable, "-c", "import time; time.sleep(120)"]
# A child that dies without writing a terminal status.
CRASHING_CHILD = [sys.executable, "-c", "import sys; sys.exit(3)"]


class TestJobQueue(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = Path(tempfile.mkdtemp(prefix="job_queue_"))
        cls.original_cwd = os.getcwd()
        cls.saved_env = {
            key: os.environ.get(key)
            for key in ("DATABASE_URL", "JWT_SECRET_KEY", "JOB_EXECUTION_MODE")
        }
        os.environ["DATABASE_URL"] = f"sqlite:///{cls.tmpdir / 'queue.db'}"
        os.environ["JWT_SECRET_KEY"] = "test-jwt-secret-with-at-least-thirty-two-bytes"
        # Worker mode: POST /api/jobs and /retry only enqueue.
        os.environ["JOB_EXECUTION_MODE"] = "worker"
        os.chdir(cls.tmpdir)
        for name in list(sys.modules):
            if name in ("backend", "worker") or name.startswith(("backend.", "worker.")):
                sys.modules.pop(name, None)

        import backend.database as database
        import backend.main as main
        from backend import job_queue
        from backend.auth import get_password_hash
        from backend.models import AppRole, User, UserRole, UserStatus
        from backend.tools.sync_registry import sync_registry
        from worker.runner import Worker

        cls.database = database
        cls.main = main
        cls.job_queue = job_queue
        cls.Worker = Worker
        with database.SessionLocal() as session:
            user = User(
                email="queue@example.com",
                hashed_password=get_password_hash("test-password"),
                full_name="Queue Owner",
                status=UserStatus.active,
            )
            session.add(user)
            session.flush()
            session.add(UserRole(user_id=user.id, role=AppRole.engineer))
            session.commit()
            sync_registry(session)
            cls.user_id = user.id

        cls.client = TestClient(main.app)
        auth = cls.client.post(
            "/api/auth/login",
            json={"email": "queue@example.com", "password": "test-password"},
        )
        auth.raise_for_status()
        cls.headers = {"Authorization": f"Bearer {auth.json()['access_token']}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        cls.database.engine.dispose()
        for name in list(sys.modules):
            if name in ("backend", "worker") or name.startswith(("backend.", "worker.")):
                sys.modules.pop(name, None)
        os.chdir(cls.original_cwd)
        for key, value in cls.saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    # -- helpers -----------------------------------------------------------

    def _new_job(self, **overrides):
        from backend.models import Job, JobStatus

        with self.database.SessionLocal() as session:
            job = Job(
                user_id=self.user_id,
                module_key="check_control",
                status=JobStatus.queued,
                input_refs={"files": [], "data_source": "db"},
            )
            for key, value in overrides.items():
                setattr(job, key, value)
            session.add(job)
            session.commit()
            return str(job.id)

    def _row(self, job_id):
        from backend.models import Job

        with self.database.SessionLocal() as session:
            job = session.query(Job).filter(Job.id == job_id).one()
            session.expunge(job)
            return job

    def _drain(self):
        from backend.models import Job, JobStatus

        with self.database.SessionLocal() as session:
            session.query(Job).filter(Job.status.in_([JobStatus.queued, JobStatus.running])).update(
                {Job.status: JobStatus.cancelled}, synchronize_session=False
            )
            session.commit()

    def setUp(self):
        self._drain()

    # -- claim & lease -----------------------------------------------------

    def test_claim_takes_oldest_queued_job_once(self):
        first = self._new_job()
        time.sleep(0.01)
        second = self._new_job()

        with self.database.SessionLocal() as db:
            claim_a = self.job_queue.claim_next_job(db, "worker-a")
            claim_b = self.job_queue.claim_next_job(db, "worker-b")
            claim_c = self.job_queue.claim_next_job(db, "worker-c")

        self.assertEqual(claim_a.job_id, first)
        self.assertEqual(claim_b.job_id, second)
        self.assertIsNone(claim_c, "nothing left to claim")

        row = self._row(first)
        self.assertEqual(row.status.value, "running")
        self.assertEqual(row.lease_owner, "worker-a")
        self.assertEqual(row.lease_token, claim_a.lease_token)
        self.assertEqual(row.attempt, 1)
        self.assertIsNotNone(row.lease_expires_at)
        self.assertIsNotNone(row.started_at)

    def test_expired_lease_is_reclaimed_with_a_new_token_and_old_writes_are_fenced(self):
        job_id = self._new_job()
        with self.database.SessionLocal() as db:
            first = self.job_queue.claim_next_job(db, "worker-a", lease_seconds=1)
            self.assertIsNotNone(first)
            # Not reclaimable while the lease is alive.
            self.assertIsNone(self.job_queue.claim_next_job(db, "worker-b"))

        time.sleep(1.2)

        with self.database.SessionLocal() as db:
            second = self.job_queue.claim_next_job(db, "worker-b")
        self.assertIsNotNone(second)
        self.assertEqual(second.job_id, job_id)
        self.assertNotEqual(second.lease_token, first.lease_token)
        self.assertEqual(second.attempt, 2)

        with self.database.SessionLocal() as db:
            stale = self.job_queue.fenced_update(db, job_id, first.lease_token, progress=55)
            fresh = self.job_queue.fenced_update(db, job_id, second.lease_token, progress=77)
            stale_heartbeat = self.job_queue.extend_lease(db, job_id, first.lease_token)
        self.assertFalse(stale, "a reclaimed worker must not write")
        self.assertTrue(fresh)
        self.assertFalse(stale_heartbeat)
        self.assertEqual(self._row(job_id).progress, 77)
        self.assertEqual(self._row(job_id).lease_owner, "worker-b")

    def test_job_that_exhausts_attempts_is_failed_not_reclaimed(self):
        from backend.models import Job, JobStatus

        job_id = self._new_job(
            status=JobStatus.running,
            attempt=3,
            lease_owner="ghost",
            lease_token="dead-token",
            lease_expires_at=self.job_queue.utcnow() - timedelta(seconds=5),
        )
        with self.database.SessionLocal() as db:
            claim = self.job_queue.claim_next_job(db, "worker-a", max_attempts=3)
        self.assertIsNone(claim)
        row = self._row(job_id)
        self.assertEqual(row.status.value, "failed")
        self.assertIn("3 attempt", row.error_message)
        self.assertIsNone(row.lease_token)

    def test_finish_clears_the_token_so_nothing_can_write_afterwards(self):
        from backend.models import JobStatus

        job_id = self._new_job()
        with self.database.SessionLocal() as db:
            claim = self.job_queue.claim_next_job(db, "worker-a")
            self.assertTrue(self.job_queue.finish(db, job_id, claim.lease_token, JobStatus.done, progress=100))
            self.assertFalse(self.job_queue.fenced_update(db, job_id, claim.lease_token, progress=1))
        row = self._row(job_id)
        self.assertEqual(row.status.value, "done")
        self.assertIsNone(row.lease_token)
        self.assertIsNotNone(row.completed_at)

    # -- worker supervision (real child processes) --------------------------

    def _worker(self, **overrides):
        options = dict(
            poll_seconds=0.1,
            lease_seconds=30,
            heartbeat_seconds=0.5,
            timeout_seconds=60,
            tick_seconds=0.1,
            child_command=SLEEPING_CHILD,
        )
        options.update(overrides)
        return self.Worker("test-worker", **options)

    def test_cancel_request_kills_the_child_and_marks_the_job_cancelled(self):
        from backend.models import Job

        job_id = self._new_job()
        with self.database.SessionLocal() as db:
            claim = self.job_queue.claim_next_job(db, "test-worker")
            db.query(Job).filter(Job.id == job_id).update({Job.cancel_requested: True})
            db.commit()

        started = time.monotonic()
        outcome = self._worker().run_claim(claim)
        self.assertEqual(outcome, "cancelled")
        self.assertLess(time.monotonic() - started, 20)
        row = self._row(job_id)
        self.assertEqual(row.status.value, "cancelled")
        self.assertFalse(row.cancel_requested)
        self.assertIsNone(row.lease_token)

    def test_timeout_kills_the_child_and_fails_the_job(self):
        job_id = self._new_job()
        with self.database.SessionLocal() as db:
            claim = self.job_queue.claim_next_job(db, "test-worker")

        outcome = self._worker(timeout_seconds=1).run_claim(claim)
        self.assertEqual(outcome, "timeout")
        row = self._row(job_id)
        self.assertEqual(row.status.value, "failed")
        self.assertIn("time limit", row.error_message)

    def test_child_crash_is_recorded_as_failure(self):
        job_id = self._new_job()
        with self.database.SessionLocal() as db:
            claim = self.job_queue.claim_next_job(db, "test-worker")

        outcome = self._worker(child_command=CRASHING_CHILD).run_claim(claim)
        self.assertEqual(outcome, "crashed")
        row = self._row(job_id)
        self.assertEqual(row.status.value, "failed")
        self.assertIn("exited with code 3", row.error_message)

    def test_lost_lease_stops_supervision_without_writing(self):
        from backend.models import Job

        job_id = self._new_job()
        with self.database.SessionLocal() as db:
            claim = self.job_queue.claim_next_job(db, "test-worker")
            # Another worker reclaimed the row (token rotated) while we ran.
            db.query(Job).filter(Job.id == job_id).update({Job.lease_token: "someone-else", Job.lease_owner: "other"})
            db.commit()

        outcome = self._worker().run_claim(claim)
        self.assertEqual(outcome, "lease_lost")
        row = self._row(job_id)
        self.assertEqual(row.status.value, "running", "the other owner's row is untouched")
        self.assertEqual(row.lease_owner, "other")

    def test_graceful_stop_releases_the_job_back_to_the_queue(self):
        job_id = self._new_job()
        with self.database.SessionLocal() as db:
            claim = self.job_queue.claim_next_job(db, "test-worker")

        worker = self._worker()
        worker.request_stop()
        outcome = worker.run_claim(claim)
        self.assertEqual(outcome, "requeued")
        row = self._row(job_id)
        self.assertEqual(row.status.value, "queued")
        self.assertIsNone(row.lease_token)
        self.assertEqual(row.attempt, 1, "the attempt still counts")

    def test_run_once_executes_a_real_job_through_the_child_process(self):
        # The real child (worker.job_child) runs check_control with no inputs,
        # which the runner rejects: the point is the round trip, not the module.
        job_id = self._new_job(input_refs={"files": [], "data_source": "files"})
        worker = self._worker(child_command=None or [sys.executable, "-m", "worker.job_child"])
        self.assertTrue(worker.run_once())
        row = self._row(job_id)
        self.assertEqual(row.status.value, "failed")
        self.assertIn("No valid input files", row.error_message)
        self.assertEqual(row.attempt, 1)
        self.assertIsNone(row.lease_token)
        self.assertFalse(worker.run_once(), "queue is now empty")

    # -- API ---------------------------------------------------------------

    def test_create_job_only_enqueues_in_worker_mode(self):
        created = self.client.post(
            "/api/jobs",
            headers=self.headers,
            json={"module_key": "check_control", "input_refs": {"files": [], "data_source": "db"}},
        )
        created.raise_for_status()
        job = self.client.get(f"/api/jobs/{created.json()['id']}", headers=self.headers).json()
        self.assertEqual(job["status"], "queued")
        self.assertEqual(job["attempt"], 0)
        self.assertFalse(job["cancel_requested"])

    def test_cancel_endpoint_semantics(self):
        from backend.models import Job, JobStatus

        queued = self._new_job()
        response = self.client.post(f"/api/jobs/{queued}/cancel", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "cancelled")

        running = self._new_job()
        with self.database.SessionLocal() as db:
            self.job_queue.claim_next_job(db, "worker-a")
        response = self.client.post(f"/api/jobs/{running}/cancel", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "running")
        self.assertTrue(response.json()["cancel_requested"])

        done = self._new_job(status=JobStatus.done)
        self.assertEqual(self.client.post(f"/api/jobs/{done}/cancel", headers=self.headers).status_code, 409)
        self.assertEqual(self.client.post("/api/jobs/nope/cancel", headers=self.headers).status_code, 404)

    def test_retry_endpoint_requeues_failed_and_cancelled_only(self):
        from backend.models import JobStatus

        failed = self._new_job(status=JobStatus.failed, error_message="boom", progress=40, attempt=1)
        response = self.client.post(f"/api/jobs/{failed}/retry", headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "queued")
        self.assertIsNone(body["error_message"])
        self.assertEqual(body["progress"], 0)
        self.assertEqual(body["attempt"], 1, "attempts keep counting across retries")

        running = self._new_job()
        with self.database.SessionLocal() as db:
            self.job_queue.claim_next_job(db, "worker-a")
        self.assertEqual(self.client.post(f"/api/jobs/{running}/retry", headers=self.headers).status_code, 409)

    def test_other_users_jobs_are_invisible_to_cancel_and_retry(self):
        from backend.auth import get_password_hash
        from backend.models import Job, JobStatus, User, UserStatus

        with self.database.SessionLocal() as session:
            other = User(
                email="other-queue@example.com",
                hashed_password=get_password_hash("test-password"),
                full_name="Other",
                status=UserStatus.active,
            )
            session.add(other)
            session.flush()
            job = Job(user_id=other.id, module_key="check_control", status=JobStatus.failed, input_refs={})
            session.add(job)
            session.commit()
            foreign = str(job.id)

        self.assertEqual(self.client.post(f"/api/jobs/{foreign}/cancel", headers=self.headers).status_code, 404)
        self.assertEqual(self.client.post(f"/api/jobs/{foreign}/retry", headers=self.headers).status_code, 404)


if __name__ == "__main__":
    unittest.main()
