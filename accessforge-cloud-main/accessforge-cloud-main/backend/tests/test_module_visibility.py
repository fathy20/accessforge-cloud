import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestModuleVisibility(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def test_missing_view_permission_omits_module_and_direct_access_is_403(self):
        self.app.create_user("viewer@example.test", roles=["viewer"])
        from backend.models import AppRole, RolePermission, UserRole

        with self.app.database.SessionLocal() as session:
            viewer_role = session.query(UserRole).filter(UserRole.user_id == self.app.user_id("viewer@example.test")).one()
            session.query(RolePermission).filter(
                RolePermission.role == viewer_role.role,
                RolePermission.permission_key == "task_extractor.view",
            ).delete(synchronize_session=False)
            session.commit()

        headers = self.app.headers("viewer@example.test")
        modules = self.app.client.get("/api/modules", headers=headers)
        self.assertEqual(modules.status_code, 200)
        self.assertNotIn("task_extractor", {module["key"] for module in modules.json()})

        direct = self.app.client.get("/api/modules/task_extractor", headers=headers)
        self.assertEqual(direct.status_code, 403)

    def test_enabled_status_and_per_user_access_filters_apply(self):
        self.app.create_user("engineer@example.test", roles=["engineer"])
        self.app.create_user("admin@example.test", roles=["super_admin"])
        admin_headers = self.app.headers("admin@example.test")
        from backend.models import Module, ModuleAccess, ModuleStatus

        with self.app.database.SessionLocal() as session:
            hidden = session.query(Module).filter(Module.key == "task_stamping").one()
            hidden.module_status = ModuleStatus.hidden
            disabled = session.query(Module).filter(Module.key == "effectivity").one()
            disabled.enabled = False
            blocked_for_user = session.query(Module).filter(Module.key == "crew_hours").one()
            session.add(
                ModuleAccess(
                    user_id=self.app.user_id("engineer@example.test"),
                    module_id=blocked_for_user.id,
                    enabled=False,
                )
            )
            session.commit()

        visible = self.app.client.get(
            "/api/modules", headers=self.app.headers("engineer@example.test")
        )
        keys = {module["key"] for module in visible.json()}
        self.assertNotIn("task_stamping", keys)
        self.assertNotIn("effectivity", keys)
        self.assertNotIn("crew_hours", keys)

        self.assertEqual(
            self.app.client.get("/api/modules/task_stamping", headers=admin_headers).status_code,
            403,
        )
        self.assertEqual(
            self.app.client.get("/api/modules/effectivity", headers=admin_headers).status_code,
            403,
        )
        self.assertEqual(
            self.app.client.get("/api/modules/unknown", headers=admin_headers).status_code,
            404,
        )


if __name__ == "__main__":
    unittest.main()
