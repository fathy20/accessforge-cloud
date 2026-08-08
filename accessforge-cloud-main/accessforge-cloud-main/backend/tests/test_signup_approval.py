import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestSignupApproval(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        self.admin_email = "approval-admin@example.test"
        self.app.create_user(self.admin_email, roles=["super_admin"])
        self.admin_headers = self.app.headers(self.admin_email)

    def tearDown(self):
        self.app.close()

    def test_signup_is_pending_has_no_role_and_returns_no_token(self):
        response = self.app.client.post(
            "/api/auth/register",
            json={
                "email": "pending@example.test",
                "password": "SIGNUP_TEST_PASSWORD_123",
                "full_name": "Pending User",
            },
        )
        self.assertEqual(response.status_code, 202)
        self.assertNotIn("access_token", response.json())
        self.assertEqual(response.json()["status"], "pending_approval")

        from backend.models import User, UserRole, UserStatus

        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.email == "pending@example.test").one()
            self.assertEqual(user.status, UserStatus.pending_approval)
            self.assertEqual(session.query(UserRole).filter(UserRole.user_id == user.id).count(), 0)

    def test_approve_activates_and_assigns_roles_and_reject_sets_rejected(self):
        pending = self.app.client.post(
            "/api/auth/register",
            json={"email": "approve@example.test", "password": "SIGNUP_TEST_PASSWORD_123"},
        )
        self.assertEqual(pending.status_code, 202)
        approve_id = self.app.user_id("approve@example.test")
        approved = self.app.client.post(
            f"/api/admin/users/{approve_id}/approve",
            headers=self.admin_headers,
            json={"roles": ["engineer"]},
        )
        self.assertEqual(approved.status_code, 200)

        from backend.models import AppRole, User, UserRole, UserStatus

        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.id == approve_id).one()
            self.assertEqual(user.status, UserStatus.active)
            self.assertEqual(
                [role.role for role in session.query(UserRole).filter(UserRole.user_id == approve_id)],
                [AppRole.engineer],
            )
        self.assertEqual(
            self.app.login("approve@example.test", "SIGNUP_TEST_PASSWORD_123").status_code,
            200,
        )

        rejected = self.app.client.post(
            "/api/auth/register",
            json={"email": "reject@example.test", "password": "SIGNUP_TEST_PASSWORD_123"},
        )
        self.assertEqual(rejected.status_code, 202)
        reject_id = self.app.user_id("reject@example.test")
        rejected_response = self.app.client.post(
            f"/api/admin/users/{reject_id}/reject",
            headers=self.admin_headers,
        )
        self.assertEqual(rejected_response.status_code, 200)
        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.id == reject_id).one()
            self.assertEqual(user.status, UserStatus.rejected)

    def test_approval_requires_pending_user_and_nonempty_roles(self):
        self.app.create_user("active-user@example.test")
        active_id = self.app.user_id("active-user@example.test")
        response = self.app.client.post(
            f"/api/admin/users/{active_id}/approve",
            headers=self.admin_headers,
            json={"roles": ["viewer"]},
        )
        self.assertEqual(response.status_code, 400)

        pending = self.app.client.post(
            "/api/auth/register",
            json={"email": "empty-roles@example.test", "password": "SIGNUP_TEST_PASSWORD_123"},
        )
        self.assertEqual(pending.status_code, 202)
        pending_id = self.app.user_id("empty-roles@example.test")
        empty = self.app.client.post(
            f"/api/admin/users/{pending_id}/approve",
            headers=self.admin_headers,
            json={"roles": []},
        )
        self.assertEqual(empty.status_code, 400)


if __name__ == "__main__":
    unittest.main()
