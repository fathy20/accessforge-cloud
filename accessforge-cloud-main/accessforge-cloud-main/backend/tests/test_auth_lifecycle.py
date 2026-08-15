import json
import os
import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestAuthLifecycle(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        self.admin_email = "lifecycle-admin@example.test"
        self.app.create_user(self.admin_email, roles=["super_admin"])
        self.admin_headers = self.app.headers(self.admin_email)

    def tearDown(self):
        self.app.close()

    def test_active_user_login_returns_access_token_contract(self):
        email = "active-login-contract@example.test"
        self.app.create_user(email)

        response = self.app.login(email)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsInstance(payload["access_token"], str)
        self.assertEqual(payload["token_type"], "bearer")
        self.assertFalse(payload["must_change_password"])

    def test_wrong_password_returns_json_authentication_failure(self):
        email = "wrong-password-contract@example.test"
        self.app.create_user(email)

        response = self.app.login(email, password=email)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Incorrect email or password")

    def test_unknown_email_matches_wrong_password_response(self):
        existing_email = "known-user-contract@example.test"
        unknown_email = "unknown-user-contract@example.test"
        self.app.create_user(existing_email)

        wrong_password = self.app.login(existing_email, password=existing_email)
        unknown_email_response = self.app.login(unknown_email, password=unknown_email)

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(unknown_email_response.status_code, 401)
        self.assertEqual(unknown_email_response.json(), wrong_password.json())

    def test_disabled_user_with_correct_password_is_rejected(self):
        from backend.models import UserStatus

        email = "disabled-login-contract@example.test"
        self.app.create_user(email, status=UserStatus.disabled)

        response = self.app.login(email)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Account is not active")

    def test_locked_user_with_correct_password_is_rejected(self):
        from backend.models import UserStatus

        email = "locked-login-contract@example.test"
        self.app.create_user(email, status=UserStatus.locked)

        response = self.app.login(email)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Account is not active")

    def test_login_failure_responses_are_json_with_string_details(self):
        from backend.models import UserStatus

        active_email = "failure-json-active@example.test"
        disabled_email = "failure-json-disabled@example.test"
        locked_email = "failure-json-locked@example.test"
        rate_limited_email = "failure-json-rate-limited@example.test"
        self.app.create_user(active_email)
        self.app.create_user(disabled_email, status=UserStatus.disabled)
        self.app.create_user(locked_email, status=UserStatus.locked)
        self.app.create_user(rate_limited_email)

        responses = [
            self.app.login(active_email, password=active_email),
            self.app.login("failure-json-unknown@example.test", password="failure-json-unknown@example.test"),
            self.app.login(disabled_email),
            self.app.login(locked_email),
        ]
        for _ in range(5):
            self.app.login(rate_limited_email, password=rate_limited_email)
        responses.append(self.app.login(rate_limited_email, password=rate_limited_email))

        for response in responses:
            self.assertTrue(response.headers["content-type"].startswith("application/json"))
            self.assertIsInstance(response.json()["detail"], str)

    def test_failed_logins_lock_account_and_admin_unlock_restores_login(self):
        from backend.auth import reset_login_rate_limit
        from backend.models import User, UserStatus

        email = "persistent-lock@example.test"
        self.app.create_user(email)
        for _ in range(5):
            response = self.app.login(email, "incorrect-password")
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json()["detail"], "Incorrect email or password")

        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.email == email).one()
            self.assertEqual(user.status, UserStatus.locked)
            self.assertEqual(user.failed_login_count, 5)
            self.assertIsNotNone(user.locked_at)

        reset_login_rate_limit(email)
        self.assertEqual(self.app.login(email).status_code, 403)

        unlock = self.app.client.post(
            f"/api/admin/users/{self.app.user_id(email)}/unlock",
            headers=self.admin_headers,
        )
        self.assertEqual(unlock.status_code, 200)
        self.assertEqual(unlock.json()["new_status"], "active")
        self.assertEqual(self.app.login(email).status_code, 200)

        not_locked = self.app.client.post(
            f"/api/admin/users/{self.app.user_id(email)}/unlock",
            headers=self.admin_headers,
        )
        self.assertEqual(not_locked.status_code, 400)
        self.assertEqual(not_locked.json()["detail"], "User is not locked")

    def test_successful_login_resets_failed_count_and_sets_last_login(self):
        from datetime import datetime, timezone

        from backend.models import User

        email = "login-reset@example.test"
        self.app.create_user(email)
        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.email == email).one()
            user.failed_login_count = 3
            user.locked_at = datetime.now(timezone.utc)
            session.commit()

        response = self.app.login(email)
        self.assertEqual(response.status_code, 200)
        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.email == email).one()
            self.assertEqual(user.failed_login_count, 0)
            self.assertIsNone(user.locked_at)
            self.assertIsNotNone(user.last_login_at)

    def test_password_change_required_can_login_but_only_change_password_route_accepts_token(self):
        from backend.models import User, UserStatus

        email = "required-password-change@example.test"
        self.app.create_user(email, status=UserStatus.password_change_required)
        login = self.app.login(email)
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["must_change_password"])
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

        self.assertEqual(self.app.client.get("/api/auth/me", headers=headers).status_code, 403)
        changed = self.app.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "current_password": "RBAC_TEST_PASSWORD_123",
                "new_password": "A_NEW_PASSWORD_12345",
            },
        )
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.json(), {"status": "success"})

        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.email == email).one()
            self.assertEqual(user.status, UserStatus.active)
            self.assertIsNotNone(user.password_changed_at)
            self.assertEqual(user.failed_login_count, 0)

        new_login = self.app.login(email, "A_NEW_PASSWORD_12345")
        self.assertEqual(new_login.status_code, 200)
        self.assertFalse(new_login.json()["must_change_password"])

    def test_change_password_validates_current_password_length_and_difference(self):
        email = "change-validation@example.test"
        self.app.create_user(email)
        headers = self.app.headers(email)

        wrong_current = self.app.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"current_password": "wrong-password", "new_password": "A_NEW_PASSWORD_12345"},
        )
        self.assertEqual(wrong_current.status_code, 400)
        self.assertEqual(wrong_current.json()["detail"], "Current password is incorrect")

        too_short = self.app.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={"current_password": "RBAC_TEST_PASSWORD_123", "new_password": "short"},
        )
        self.assertEqual(too_short.status_code, 400)
        self.assertEqual(too_short.json()["detail"], "Password must be at least 12 characters long")

        unchanged = self.app.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "current_password": "RBAC_TEST_PASSWORD_123",
                "new_password": "RBAC_TEST_PASSWORD_123",
            },
        )
        self.assertEqual(unchanged.status_code, 400)
        self.assertEqual(unchanged.json()["detail"], "New password must differ from the current password")

        valid = self.app.client.post(
            "/api/auth/change-password",
            headers=headers,
            json={
                "current_password": "RBAC_TEST_PASSWORD_123",
                "new_password": "A_DIFFERENT_PASSWORD_12345",
            },
        )
        self.assertEqual(valid.status_code, 200)
        self.assertEqual(self.app.login(email, "A_DIFFERENT_PASSWORD_12345").status_code, 200)

    def test_admin_reset_password_returns_one_time_temporary_password_without_audit_secret(self):
        from backend.models import AuditLog, User, UserStatus

        email = "reset-target@example.test"
        self.app.create_user(email)
        user_id = self.app.user_id(email)
        response = self.app.client.post(
            f"/api/admin/users/{user_id}/reset-password",
            headers=self.admin_headers,
        )
        self.assertEqual(response.status_code, 200)
        temporary_password = response.json()["temporary_password"]
        self.assertGreaterEqual(len(temporary_password), 16)

        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.id == user_id).one()
            self.assertEqual(user.status, UserStatus.password_change_required)
            self.assertEqual(user.failed_login_count, 0)
            self.assertIsNone(user.locked_at)
            self.assertIsNotNone(user.password_changed_at)
            reset_audit = (
                session.query(AuditLog)
                .filter(AuditLog.action == "password_reset", AuditLog.entity_id == user_id)
                .one()
            )
            self.assertEqual(
                reset_audit.metadata_json,
                {"target_status": UserStatus.password_change_required.value},
            )
            self.assertNotIn(temporary_password, json.dumps(reset_audit.metadata_json))

        login = self.app.login(email, temporary_password)
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.json()["must_change_password"])

    def test_admin_user_creation_returns_usable_temporary_password_and_assigns_roles(self):
        from backend.models import AuditLog, AppRole, User, UserRole, UserStatus

        response = self.app.client.post(
            "/api/admin/users",
            headers=self.admin_headers,
            json={
                "email": "created-admin-user@example.test",
                "full_name": "Created User",
                "roles": ["viewer", "engineer"],
            },
        )
        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertGreaterEqual(len(payload["temporary_password"]), 16)
        self.assertEqual(payload["status"], UserStatus.password_change_required.value)
        self.assertEqual(payload["roles"], ["viewer", "engineer"])
        self.assertEqual(
            self.app.login(payload["email"], payload["temporary_password"]).status_code,
            200,
        )

        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.id == payload["id"]).one()
            self.assertEqual(
                {role.role for role in session.query(UserRole).filter(UserRole.user_id == user.id)},
                {AppRole.viewer, AppRole.engineer},
            )
            actions = [
                row.action
                for row in session.query(AuditLog).filter(AuditLog.entity_id == user.id).all()
            ]
            self.assertIn("admin_user_creation", actions)
            self.assertEqual(actions.count("role_assignment"), 2)

    def test_plain_admin_cannot_create_super_admin(self):
        email = "plain-create-admin@example.test"
        self.app.create_user(email, roles=["admin"])
        response = self.app.client.post(
            "/api/admin/users",
            headers=self.app.headers(email),
            json={"email": "forbidden-super@example.test", "full_name": None, "roles": ["super_admin"]},
        )
        self.assertEqual(response.status_code, 403)

    def test_plain_admin_cannot_approve_super_admin(self):
        self.app.create_user("plain-approve-admin@example.test", roles=["admin"])
        pending = self.app.client.post(
            "/api/auth/register",
            json={"email": "pending-super@example.test", "password": "PENDING_PASSWORD_12345"},
        )
        self.assertEqual(pending.status_code, 202)
        response = self.app.client.post(
            f"/api/admin/users/{self.app.user_id('pending-super@example.test')}/approve",
            headers=self.app.headers("plain-approve-admin@example.test"),
            json={"roles": ["super_admin"]},
        )
        self.assertEqual(response.status_code, 403)

    def test_pending_signup_has_empty_effective_permissions(self):
        from backend.models import User, UserRole, UserStatus
        from backend.rbac.permissions import get_effective_permissions

        email = "pending-no-permissions@example.test"
        response = self.app.client.post(
            "/api/auth/register",
            json={"email": email, "password": "PENDING_PASSWORD_12345"},
        )
        self.assertEqual(response.status_code, 202)
        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.email == email).one()
            self.assertEqual(user.status, UserStatus.pending_approval)
            self.assertEqual(session.query(UserRole).filter(UserRole.user_id == user.id).count(), 0)
            self.assertEqual(get_effective_permissions(session, user), set())

    def test_self_signup_can_be_disabled_and_enabled(self):
        original_flag = os.environ.get("SELF_SIGNUP_ENABLED")
        self.app.close()
        disabled_app = None
        try:
            os.environ["SELF_SIGNUP_ENABLED"] = "false"
            disabled_app = AppHarness()
            disabled = disabled_app.client.post(
                "/api/auth/register",
                json={"email": "disabled-signup@example.test", "password": "DISABLED_PASSWORD_123"},
            )
            self.assertEqual(disabled.status_code, 403)
            self.assertEqual(disabled.json()["detail"], "Self-signup is disabled")
        finally:
            if disabled_app is not None:
                disabled_app.close()
            if original_flag is None:
                os.environ.pop("SELF_SIGNUP_ENABLED", None)
            else:
                os.environ["SELF_SIGNUP_ENABLED"] = original_flag

        self.app = AppHarness()
        enabled = self.app.client.post(
            "/api/auth/register",
            json={"email": "enabled-signup@example.test", "password": "ENABLED_PASSWORD_123"},
        )
        self.assertEqual(enabled.status_code, 202)


if __name__ == "__main__":
    unittest.main()
