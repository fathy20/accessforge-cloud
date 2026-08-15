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
        from backend.models import AppRole, RolePermission, UserRole

        with self.app.database.SessionLocal() as session:
            session.query(UserRole).filter(
                UserRole.user_id == self.app.user_id(self.admin_email)
            ).delete(synchronize_session=False)
            session.commit()

        self.app.create_user("ordinary-admin@example.test", roles=["admin"])
        self.app.create_user("only-super@example.test", roles=["super_admin"])
        with self.app.database.SessionLocal() as session:
            session.add(
                RolePermission(
                    role=AppRole.admin,
                    permission_key="admin.roles.manage_super_admin",
                )
            )
            session.commit()
        target_id = self.app.user_id("only-super@example.test")
        ordinary_headers = self.app.headers("ordinary-admin@example.test")

        response = self.app.client.post(
            f"/api/admin/users/{target_id}/roles",
            headers=ordinary_headers,
            json={"roles": []},
        )
        self.assertEqual(response.status_code, 409)

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

    def test_plain_admin_cannot_grant_super_admin_even_to_themselves(self):
        self.app.create_user("plain-admin@example.test", roles=["admin"])
        plain_admin_id = self.app.user_id("plain-admin@example.test")
        headers = self.app.headers("plain-admin@example.test")

        for target_id, roles in (
            (plain_admin_id, ["admin", "super_admin"]),
            (
                self.app.create_user("grant-attempt-target@example.test", roles=["viewer"]),
                ["viewer", "super_admin"],
            ),
        ):
            response = self.app.client.post(
                f"/api/admin/users/{target_id}/roles",
                headers=headers,
                json={"roles": roles},
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(
                response.json()["detail"],
                "Super-admin role changes require the admin.roles.manage_super_admin permission",
            )

    def test_super_admin_can_grant_super_admin(self):
        target_id = self.app.create_user("grant-target@example.test", roles=["viewer"])
        response = self.app.client.post(
            f"/api/admin/users/{target_id}/roles",
            headers=self.headers,
            json={"roles": ["viewer", "super_admin"]},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("super_admin", response.json()["roles"])

    def test_plain_admin_cannot_remove_super_admin_from_another_user(self):
        self.app.create_user("plain-admin-remove@example.test", roles=["admin"])
        target_id = self.app.create_user("remove-target@example.test", roles=["super_admin"])
        response = self.app.client.post(
            f"/api/admin/users/{target_id}/roles",
            headers=self.app.headers("plain-admin-remove@example.test"),
            json={"roles": []},
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "Super-admin role changes require the admin.roles.manage_super_admin permission",
        )

    def test_last_active_super_admin_cannot_be_deactivated(self):
        from backend.models import UserRole

        with self.app.database.SessionLocal() as session:
            session.query(UserRole).filter(
                UserRole.user_id == self.app.user_id(self.admin_email)
            ).delete(synchronize_session=False)
            session.commit()

        self.app.create_user("status-admin@example.test", roles=["admin"])
        target_id = self.app.create_user("last-active-super@example.test", roles=["super_admin"])
        headers = self.app.headers("status-admin@example.test")
        response = self.app.client.post(
            f"/api/admin/users/{target_id}/status",
            headers=headers,
            json={"status": "disabled"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"], "The last active super-admin cannot be deactivated")

        self.app.create_user("second-active-super@example.test", roles=["super_admin"])
        response = self.app.client.post(
            f"/api/admin/users/{target_id}/status",
            headers=headers,
            json={"status": "disabled"},
        )
        self.assertEqual(response.status_code, 200)

    def test_plain_admin_cannot_reset_a_super_admin_password(self):
        from backend.models import User, UserStatus

        self.app.create_user("reset-plain-admin@example.test", roles=["admin"])
        target_id = self.app.create_user("reset-super-target@example.test", roles=["super_admin"])
        with self.app.database.SessionLocal() as session:
            target = session.query(User).filter(User.id == target_id).one()
            original_hash = target.hashed_password
            original_status = target.status

        response = self.app.client.post(
            f"/api/admin/users/{target_id}/reset-password",
            headers=self.app.headers("reset-plain-admin@example.test"),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            response.json()["detail"],
            "Resetting a super-admin password requires the admin.roles.manage_super_admin permission",
        )

        with self.app.database.SessionLocal() as session:
            target = session.query(User).filter(User.id == target_id).one()
            self.assertEqual(target.status, original_status)
            self.assertEqual(target.status, UserStatus.active)
            self.assertEqual(target.hashed_password, original_hash)

    def test_super_admin_can_reset_a_super_admin_password(self):
        from backend.models import User, UserStatus

        target_id = self.app.create_user("reset-super-by-super@example.test", roles=["super_admin"])
        response = self.app.client.post(
            f"/api/admin/users/{target_id}/reset-password",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["temporary_password"]), 16)

        with self.app.database.SessionLocal() as session:
            target = session.query(User).filter(User.id == target_id).one()
            self.assertEqual(target.status, UserStatus.password_change_required)

    def test_plain_admin_can_still_reset_a_non_super_admin_password(self):
        from backend.models import User, UserStatus

        self.app.create_user("reset-ordinary-admin@example.test", roles=["admin"])
        target_id = self.app.create_user("reset-ordinary-target@example.test", roles=["viewer"])
        response = self.app.client.post(
            f"/api/admin/users/{target_id}/reset-password",
            headers=self.app.headers("reset-ordinary-admin@example.test"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(response.json()["temporary_password"]), 16)

        with self.app.database.SessionLocal() as session:
            target = session.query(User).filter(User.id == target_id).one()
            self.assertEqual(target.status, UserStatus.password_change_required)


if __name__ == "__main__":
    unittest.main()
