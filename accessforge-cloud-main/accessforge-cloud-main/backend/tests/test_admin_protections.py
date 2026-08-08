import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestAdminProtections(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()
        self.admin_email = "protection-admin@example.test"
        self.app.create_user(self.admin_email, roles=["super_admin"])
        self.headers = self.app.headers(self.admin_email)

    def tearDown(self):
        self.app.close()

    def test_removing_last_super_admin_is_refused_and_survives(self):
        from backend.models import UserRole

        with self.app.database.SessionLocal() as session:
            session.query(UserRole).filter(
                UserRole.user_id == self.app.user_id(self.admin_email)
            ).delete(synchronize_session=False)
            session.commit()

        self.app.create_user("ordinary-admin@example.test", roles=["admin"])
        self.app.create_user("only-super@example.test", roles=["super_admin"])
        target_id = self.app.user_id("only-super@example.test")
        ordinary_headers = self.app.headers("ordinary-admin@example.test")

        response = self.app.client.post(
            f"/api/admin/users/{target_id}/roles",
            headers=ordinary_headers,
            json={"roles": []},
        )
        self.assertEqual(response.status_code, 409)

        from backend.models import AppRole, UserRole

        with self.app.database.SessionLocal() as session:
            self.assertEqual(
                session.query(UserRole)
                .filter(UserRole.user_id == target_id, UserRole.role == AppRole.super_admin)
                .count(),
                1,
            )

    def test_self_removal_of_super_admin_is_refused(self):
        admin_id = self.app.user_id(self.admin_email)
        response = self.app.client.post(
            f"/api/admin/users/{admin_id}/roles",
            headers=self.headers,
            json={"roles": []},
        )
        self.assertEqual(response.status_code, 409)

        from backend.models import AppRole, UserRole

        with self.app.database.SessionLocal() as session:
            self.assertEqual(
                session.query(UserRole)
                .filter(UserRole.user_id == admin_id, UserRole.role == AppRole.super_admin)
                .count(),
                1,
            )

    def test_self_disable_is_refused(self):
        admin_id = self.app.user_id(self.admin_email)
        response = self.app.client.post(
            f"/api/admin/users/{admin_id}/status",
            headers=self.headers,
            json={"status": "disabled"},
        )
        self.assertEqual(response.status_code, 409)

        from backend.models import User, UserStatus

        with self.app.database.SessionLocal() as session:
            self.assertEqual(session.query(User).filter(User.id == admin_id).one().status, UserStatus.active)

    def test_admin_route_requires_explicit_permission_not_just_a_role(self):
        self.app.create_user("viewer@example.test", roles=["viewer"])
        response = self.app.client.get(
            "/api/admin/users", headers=self.app.headers("viewer@example.test")
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
