import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestAccountLifecycle(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def test_only_active_accounts_can_login(self):
        from backend.models import UserStatus

        blocked_statuses = (
            UserStatus.pending_approval,
            UserStatus.disabled,
            UserStatus.locked,
            UserStatus.rejected,
            UserStatus.password_change_required,
        )
        for index, account_status in enumerate(blocked_statuses):
            email = f"blocked-{index}@example.test"
            self.app.create_user(email, status=account_status)
            response = self.app.login(email)
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["detail"], "Account is not active")

        self.app.create_user("active@example.test", status=UserStatus.active)
        self.assertEqual(self.app.login("active@example.test").status_code, 200)

    def test_wrong_password_is_checked_before_status_gate(self):
        from backend.models import UserStatus

        self.app.create_user("disabled@example.test", status=UserStatus.disabled)
        response = self.app.login("disabled@example.test", "wrong-password")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "Incorrect email or password")

    def test_already_issued_token_stops_working_after_disable(self):
        from backend.models import User, UserStatus

        self.app.create_user("token-user@example.test", status=UserStatus.active)
        headers = self.app.headers("token-user@example.test")

        with self.app.database.SessionLocal() as session:
            user = session.query(User).filter(User.email == "token-user@example.test").one()
            user.status = UserStatus.disabled
            session.commit()

        response = self.app.client.get("/api/auth/me", headers=headers)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["detail"], "Account is not active")


if __name__ == "__main__":
    unittest.main()
