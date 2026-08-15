import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from backend.tests.test_rbac_permissions import AppHarness


MODULE_KEY = "check_control"


class TestJobModuleAuthorization(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        self.output_dir = Path(self.app.tmpdir) / "job_outputs"
        self.output_dir.mkdir()
        self.app.main.OUTPUT_DIR = self.output_dir

    def tearDown(self):
        self.app.close()

    def submit_job(self, email, input_refs=None):
        return self.app.client.post(
            "/api/jobs",
            headers=self.app.headers(email),
            json={
                "module_key": MODULE_KEY,
                "input_refs": input_refs or {"files": [], "data_source": "db"},
            },
        )

    def job_count(self, email):
        from backend.models import Job

        with self.app.database.SessionLocal() as session:
            return (
                session.query(Job)
                .filter(Job.user_id == self.app.user_id(email))
                .count()
            )

    def test_denied_submission_matches_module_endpoint_and_creates_no_job(self):
        email = "job-module-guest@example.test"
        rejected_file = "/private/customer/input.csv"
        self.app.create_user(email, roles=["guest"])
        headers = self.app.headers(email)

        direct = self.app.client.get(f"/api/modules/{MODULE_KEY}", headers=headers)
        submitted = self.app.client.post(
            "/api/jobs",
            headers=headers,
            json={
                "module_key": MODULE_KEY,
                "input_refs": {"files": [rejected_file], "data_source": "files"},
            },
        )

        self.assertEqual(direct.status_code, 403)
        self.assertEqual(submitted.status_code, 403)
        self.assertEqual(submitted.content, direct.content)
        self.assertEqual(self.job_count(email), 0)

        from backend.models import AuditLog

        with self.app.database.SessionLocal() as session:
            event = (
                session.query(AuditLog)
                .filter(
                    AuditLog.action == "job_module_denied",
                    AuditLog.entity == "job",
                    AuditLog.entity_id.is_(None),
                )
                .one()
            )
            self.assertEqual(event.metadata_json, {"module_key": MODULE_KEY})
            serialized_metadata = json.dumps(event.metadata_json)
            self.assertNotIn(email, serialized_metadata)
            self.assertNotIn("check_control.view", serialized_metadata)
            self.assertNotIn(rejected_file, serialized_metadata)

    def test_roleless_user_is_denied_without_creating_job(self):
        email = "job-module-roleless@example.test"
        self.app.create_user(email)

        response = self.submit_job(email)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Module access denied"})
        self.assertEqual(self.job_count(email), 0)

    def test_authorized_user_can_submit_job(self):
        email = "job-module-engineer@example.test"
        self.app.create_user(email, roles=["engineer"])

        with patch.object(self.app.main, "run_job_background") as background_runner:
            response = self.submit_job(email)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "queued")
        self.assertEqual(self.job_count(email), 1)
        background_runner.assert_called_once_with(response.json()["id"])

    def test_explicit_module_disable_denies_authorized_user(self):
        email = "job-module-disabled@example.test"
        user_id = self.app.create_user(email, roles=["engineer"])
        from backend.models import Module, ModuleAccess

        with self.app.database.SessionLocal() as session:
            module = session.query(Module).filter(Module.key == MODULE_KEY).one()
            session.add(
                ModuleAccess(
                    user_id=user_id,
                    module_id=module.id,
                    enabled=False,
                )
            )
            session.commit()

        response = self.submit_job(email)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Module access denied"})
        self.assertEqual(self.job_count(email), 0)

    def test_tampered_projection_permission_is_denied_fail_closed(self):
        email = "job-module-drift@example.test"
        self.app.create_user(email, roles=["engineer"])
        from backend.models import Module

        with self.app.database.SessionLocal() as session:
            module = session.query(Module).filter(Module.key == MODULE_KEY).one()
            module.required_view_permission = "task_extractor.view"
            session.commit()

        response = self.submit_job(email)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Module access denied"})
        self.assertEqual(self.job_count(email), 0)

    def test_revoked_permission_fails_queued_job_before_handler_execution(self):
        email = "job-module-revoked@example.test"
        user_id = self.app.create_user(email, roles=["engineer"])
        from backend.models import AppRole, AuditLog, Job, JobStatus, RolePermission

        with self.app.database.SessionLocal() as session:
            job = Job(
                user_id=user_id,
                module_key=MODULE_KEY,
                status=JobStatus.queued,
                input_refs={"files": [], "data_source": "db"},
            )
            session.add(job)
            session.commit()
            job_id = str(job.id)

            session.query(RolePermission).filter(
                RolePermission.role == AppRole.engineer,
                RolePermission.permission_key == "check_control.view",
            ).delete(synchronize_session=False)
            session.commit()

        from worker import handlers

        handler = Mock(name="check_control_handler")
        with patch.dict(handlers.REGISTRY, {MODULE_KEY: handler}):
            self.app.main.run_job_background(job_id)

        handler.assert_not_called()
        with self.app.database.SessionLocal() as session:
            job = session.query(Job).filter(Job.id == job_id).one()
            self.assertEqual(job.status, JobStatus.failed)
            self.assertEqual(job.error_message, "Module access denied")
            self.assertFalse((job.output_refs or {}).get("files"))
            event = (
                session.query(AuditLog)
                .filter(
                    AuditLog.action == "job_module_denied",
                    AuditLog.entity == "job",
                    AuditLog.entity_id == job_id,
                )
                .one()
            )
            self.assertEqual(event.metadata_json, {"module_key": MODULE_KEY})

        self.assertEqual(list(self.output_dir.rglob("*")), [])

    def test_worker_only_module_key_is_denied_fail_closed(self):
        email = "job-module-orphan@example.test"
        self.app.create_user(email, roles=["engineer"])
        from worker import handlers

        orphan_handler = Mock(name="orphan_handler")
        with patch.dict(handlers.REGISTRY, {"worker_only": orphan_handler}):
            response = self.app.client.post(
                "/api/jobs",
                headers=self.app.headers(email),
                json={
                    "module_key": "worker_only",
                    "input_refs": {"files": [], "data_source": "db"},
                },
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json(), {"detail": "Module access denied"})
        self.assertEqual(self.job_count(email), 0)
        orphan_handler.assert_not_called()


if __name__ == "__main__":
    unittest.main()
