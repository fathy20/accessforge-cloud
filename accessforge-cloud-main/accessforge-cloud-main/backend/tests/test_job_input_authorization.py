import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid

from backend.tests.test_rbac_permissions import AppHarness


CSV_CONTENT = b"CHECK,TASK\nA1,27-001-00\n"


class TestJobInputAuthorization(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        self.user_a_email = "job-input-owner@example.test"
        self.user_b_email = "job-input-requester@example.test"
        self.app.create_user(self.user_a_email, roles=["engineer"])
        self.app.create_user(self.user_b_email, roles=["engineer"])
        self.headers_b = self.app.headers(self.user_b_email)
        self.storage_tmp = Path(tempfile.mkdtemp(prefix="job_input_authorization_"))
        self.output_dir = self.storage_tmp / "outputs"
        self.output_dir.mkdir()
        self.app.main.OUTPUT_DIR = self.output_dir

    def tearDown(self):
        self.app.close()
        shutil.rmtree(self.storage_tmp, ignore_errors=True)

    def add_upload(self, email, contents=CSV_CONTENT, original_name="input.csv"):
        from backend.models import Upload, UploadKind

        path = self.storage_tmp / f"{uuid.uuid4()}_{original_name}"
        path.write_bytes(contents)
        with self.app.database.SessionLocal() as session:
            upload = Upload(
                user_id=self.app.user_id(email),
                original_name=original_name,
                storage_path=str(path),
                kind=UploadKind.csv,
                mime="text/csv",
                size_bytes=len(contents),
            )
            session.add(upload)
            session.commit()
            return str(upload.id)

    def submit_job(self, input_refs):
        return self.app.client.post(
            "/api/jobs",
            headers=self.headers_b,
            json={"module_key": "check_control", "input_refs": input_refs},
        )

    def test_other_users_upload_is_rejected_without_creating_job(self):
        upload_id = self.add_upload(self.user_a_email)

        response = self.submit_job({"files": [upload_id], "data_source": "files"})

        self.assertEqual(response.status_code, 400)
        with self.app.database.SessionLocal() as session:
            self.assertEqual(
                session.query(self.app.main.Job)
                .filter(self.app.main.Job.user_id == self.app.user_id(self.user_b_email))
                .count(),
                0,
            )

    def test_other_users_upload_and_unknown_id_have_identical_error_bodies(self):
        upload_id = self.add_upload(self.user_a_email)

        inaccessible = self.submit_job({"files": [upload_id], "data_source": "files"})
        unknown = self.submit_job({"files": [str(uuid.uuid4())], "data_source": "files"})

        self.assertEqual(inaccessible.status_code, 400)
        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(inaccessible.content, unknown.content)

    def test_own_upload_is_accepted(self):
        upload_id = self.add_upload(self.user_b_email)

        response = self.submit_job(
            {"files": [upload_id], "check": "A1", "data_source": "files"}
        )

        self.assertEqual(response.status_code, 200, response.text)
        with self.app.database.SessionLocal() as session:
            job = session.query(self.app.main.Job).filter(self.app.main.Job.id == response.json()["id"]).one()
            self.assertEqual(job.status.value, "done")

    def test_db_data_source_can_submit_without_files(self):
        response = self.submit_job({"files": [], "data_source": "db"})

        self.assertEqual(response.status_code, 200, response.text)
        with self.app.database.SessionLocal() as session:
            self.assertIsNotNone(
                session.query(self.app.main.Job)
                .filter(self.app.main.Job.id == response.json()["id"])
                .one()
            )

    def test_execution_rejects_cross_tenant_input_and_produces_no_output(self):
        from backend.models import AuditLog, Job, JobStatus

        upload_id = self.add_upload(self.user_a_email, b"CONFIDENTIAL USER A CONTENT\n")
        user_b_id = self.app.user_id(self.user_b_email)
        with self.app.database.SessionLocal() as session:
            job = Job(
                user_id=user_b_id,
                module_key="check_control",
                status=JobStatus.queued,
                input_refs={
                    "files": [upload_id],
                    "check": "A1",
                    "data_source": "files",
                },
            )
            session.add(job)
            session.commit()
            job_id = str(job.id)

        self.app.main.run_job_background(job_id)

        with self.app.database.SessionLocal() as session:
            job = session.query(Job).filter(Job.id == job_id).one()
            self.assertEqual(job.status, JobStatus.failed)
            self.assertIn("unavailable", job.error_message)
            self.assertNotIn("CONFIDENTIAL USER A CONTENT", json.dumps(job.output_refs or {}))
            event = (
                session.query(AuditLog)
                .filter(AuditLog.action == "job_input_rejected", AuditLog.entity_id == job_id)
                .one()
            )
            self.assertEqual(event.metadata_json["rejected_count"], 1)
            self.assertNotIn(upload_id, json.dumps(event.metadata_json))

        self.assertEqual(list(self.output_dir.rglob("*")), [])

    def test_rejected_submission_audits_count_without_upload_id(self):
        from backend.models import AuditLog

        upload_id = self.add_upload(self.user_a_email)

        response = self.submit_job({"files": [upload_id], "data_source": "files"})

        self.assertEqual(response.status_code, 400)
        with self.app.database.SessionLocal() as session:
            event = (
                session.query(AuditLog)
                .filter(
                    AuditLog.action == "job_input_rejected",
                    AuditLog.entity == "job",
                    AuditLog.entity_id.is_(None),
                )
                .one()
            )
            self.assertEqual(event.metadata_json["rejected_count"], 1)
            self.assertNotIn(upload_id, json.dumps(event.metadata_json))


if __name__ == "__main__":
    unittest.main()
