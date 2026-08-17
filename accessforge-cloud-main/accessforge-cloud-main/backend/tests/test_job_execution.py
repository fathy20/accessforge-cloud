"""Job execution correctness: timestamps, bounded logs, resilient completion."""

import io
import unittest
from unittest.mock import patch

from backend.tests.test_rbac_permissions import AppHarness


class TestJobExecution(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        from pathlib import Path

        self.output_dir = Path(self.app.tmpdir) / "job_outputs"
        self.output_dir.mkdir()
        self.app.main.OUTPUT_DIR = self.output_dir

    def tearDown(self):
        self.app.close()

    def _run_check_control_job(self, email):
        headers = self.app.headers(email)
        uploaded = self.app.client.post(
            "/api/uploads",
            headers=headers,
            files={"files": ("checks.csv", io.BytesIO(b"CHECK\nA1\nA2\n"), "text/csv")},
        )
        uploaded.raise_for_status()
        upload_id = uploaded.json()[0]["id"]

        created = self.app.client.post(
            "/api/jobs",
            headers=headers,
            json={
                "module_key": "check_control",
                "input_refs": {"files": [upload_id], "check": "A2", "data_source": "files"},
            },
        )
        created.raise_for_status()
        return created.json()["id"], headers

    def test_completed_job_records_started_and_completed_timestamps(self):
        self.app.create_user("job-times@example.test", roles=["engineer"])
        job_id, headers = self._run_check_control_job("job-times@example.test")

        job = self.app.client.get(f"/api/jobs/{job_id}", headers=headers).json()
        self.assertEqual(job["status"], "done")
        self.assertIsNotNone(job["started_at"])
        self.assertIsNotNone(job["completed_at"])
        self.assertLessEqual(job["started_at"], job["completed_at"])

    def test_failed_job_records_completed_at_and_bounded_error(self):
        self.app.create_user("job-fail@example.test", roles=["engineer"])
        from worker import handlers

        def exploding_handler(job, input_files, workdir, log):
            raise RuntimeError("kaboom " + "x" * 5000)

        with patch.dict(handlers.REGISTRY, {"check_control": exploding_handler}):
            job_id, headers = self._run_check_control_job("job-fail@example.test")

        job = self.app.client.get(f"/api/jobs/{job_id}", headers=headers).json()
        self.assertEqual(job["status"], "failed")
        self.assertIsNotNone(job["completed_at"])
        self.assertLessEqual(len(job["error_message"]), 2000)

    def test_job_log_entries_are_bounded(self):
        from backend.main import MAX_JOB_LOG_ENTRIES, _append_job_log

        logs = []
        for index in range(MAX_JOB_LOG_ENTRIES + 50):
            logs = _append_job_log(logs, {"level": 1, "msg": f"entry {index}"})

        self.assertEqual(len(logs), MAX_JOB_LOG_ENTRIES)
        # Oldest entries fall off; the newest survive.
        self.assertEqual(logs[-1]["msg"], f"entry {MAX_JOB_LOG_ENTRIES + 49}")
        self.assertEqual(logs[0]["msg"], "entry 50")


if __name__ == "__main__":
    unittest.main()
