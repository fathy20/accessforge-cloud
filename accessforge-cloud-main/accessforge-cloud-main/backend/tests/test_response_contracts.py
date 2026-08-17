"""Response-shape contracts: no server internals leak through list endpoints."""

import io
import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestResponseContracts(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def test_upload_listing_never_contains_storage_paths(self):
        self.app.create_user("shapes@example.test", roles=["engineer"])
        headers = self.app.headers("shapes@example.test")

        created = self.app.client.post(
            "/api/uploads",
            headers=headers,
            files={"files": ("checks.csv", io.BytesIO(b"CHECK\nA1\n"), "text/csv")},
        )
        self.assertEqual(created.status_code, 200, created.text)

        listing = self.app.client.get("/api/uploads", headers=headers)
        self.assertEqual(listing.status_code, 200)
        rows = listing.json()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertNotIn("storage_path", row)
        self.assertNotIn("user_id", row)
        self.assertNotIn("metadata_json", row)
        self.assertEqual(row["original_name"], "checks.csv")
        self.assertEqual(row["kind"], "csv")
        self.assertTrue(row["sha256"])

        # The upload response itself follows the same shape.
        self.assertNotIn("storage_path", created.json()[0])

    def test_job_payload_excludes_logs_and_input_refs(self):
        from backend.models import Job, JobStatus

        user_id = self.app.create_user("job-shapes@example.test", roles=["engineer"])
        with self.app.database.SessionLocal() as session:
            job = Job(
                user_id=user_id,
                module_key="check_control",
                status=JobStatus.failed,
                input_refs={"files": ["u-1"], "data_source": "files"},
                error_message="boom",
                logs=[{"level": 99, "msg": "Traceback (most recent call last): ..."}],
            )
            session.add(job)
            session.commit()
            job_id = str(job.id)

        headers = self.app.headers("job-shapes@example.test")
        one = self.app.client.get(f"/api/jobs/{job_id}", headers=headers)
        many = self.app.client.get("/api/jobs", headers=headers)

        for payload in (one.json(), many.json()[0]):
            self.assertNotIn("logs", payload)
            self.assertNotIn("input_refs", payload)
            self.assertNotIn("user_id", payload)
            self.assertEqual(payload["error_message"], "boom")
            self.assertEqual(payload["status"], "failed")
        self.assertNotIn("Traceback", one.text)

    def test_jobs_limit_is_bounded(self):
        self.app.create_user("limits@example.test", roles=["engineer"])
        headers = self.app.headers("limits@example.test")

        too_big = self.app.client.get("/api/jobs?limit=100000", headers=headers)
        self.assertEqual(too_big.status_code, 422)
        zero = self.app.client.get("/api/jobs?limit=0", headers=headers)
        self.assertEqual(zero.status_code, 422)
        ok = self.app.client.get("/api/jobs?limit=200", headers=headers)
        self.assertEqual(ok.status_code, 200)


if __name__ == "__main__":
    unittest.main()
