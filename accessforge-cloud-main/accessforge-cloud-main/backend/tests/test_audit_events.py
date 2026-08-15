import json
import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestAuditEvents(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        self.admin_email = "audit-admin@example.test"
        self.app.create_user(self.admin_email, roles=["super_admin"])
        self.headers = self.app.headers(self.admin_email)

    def tearDown(self):
        self.app.close()

    def test_auth_approval_rejection_and_role_changes_are_audited(self):
        self.assertEqual(self.app.login(self.admin_email).status_code, 200)
        self.assertEqual(self.app.login(self.admin_email, "wrong-password").status_code, 401)

        signup = self.app.client.post(
            "/api/auth/register",
            json={"email": "audit-approve@example.test", "password": "AUDIT_TEST_PASSWORD_123"},
        )
        self.assertEqual(signup.status_code, 202)
        approve_id = self.app.user_id("audit-approve@example.test")
        approval = self.app.client.post(
            f"/api/admin/users/{approve_id}/approve",
            headers=self.headers,
            json={"roles": ["engineer"]},
        )
        self.assertEqual(approval.status_code, 200)

        rejected_signup = self.app.client.post(
            "/api/auth/register",
            json={"email": "audit-reject@example.test", "password": "AUDIT_TEST_PASSWORD_123"},
        )
        self.assertEqual(rejected_signup.status_code, 202)
        reject_id = self.app.user_id("audit-reject@example.test")
        rejection = self.app.client.post(
            f"/api/admin/users/{reject_id}/reject", headers=self.headers
        )
        self.assertEqual(rejection.status_code, 200)

        self.app.create_user("role-target@example.test", roles=["viewer"])
        role_target_id = self.app.user_id("role-target@example.test")
        assigned = self.app.client.post(
            f"/api/admin/users/{role_target_id}/roles",
            headers=self.headers,
            json={"roles": ["engineer"]},
        )
        self.assertEqual(assigned.status_code, 200)
        removed = self.app.client.post(
            f"/api/admin/users/{role_target_id}/roles",
            headers=self.headers,
            json={"roles": []},
        )
        self.assertEqual(removed.status_code, 200)

        from backend.models import AuditLog

        with self.app.database.SessionLocal() as session:
            logs = session.query(AuditLog).all()
            actions = {log.action for log in logs}
            metadata = [log.metadata_json or {} for log in logs]

        for action in (
            "login_success",
            "login_failure",
            "signup",
            "approval",
            "rejection",
            "role_assignment",
            "role_removal",
        ):
            self.assertIn(action, actions)
        serialized = json.dumps(metadata).casefold()
        self.assertNotIn("password", serialized)
        self.assertNotIn("hashed_password", serialized)
        self.assertNotIn("token", serialized)

    def test_audit_helper_filters_sensitive_metadata(self):
        from backend.models import AuditLog
        from backend.rbac.permissions import record_audit

        with self.app.database.SessionLocal() as session:
            record_audit(
                session,
                None,
                "test_audit",
                "test",
                "one",
                password="do-not-store",
                password_hash="do-not-store",
                access_token="do-not-store",
                safe="kept",
            )
            session.commit()
            log = session.query(AuditLog).filter(AuditLog.action == "test_audit").one()
            self.assertEqual(log.metadata_json, {"safe": "kept"})


if __name__ == "__main__":
    unittest.main()
