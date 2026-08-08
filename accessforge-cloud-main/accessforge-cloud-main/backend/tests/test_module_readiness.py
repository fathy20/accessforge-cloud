import unittest

from backend.tests.test_rbac_permissions import AppHarness


class TestModuleReadiness(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def test_every_registry_definition_declares_readiness(self):
        from backend.rbac.registry import MODULE_REGISTRY

        for definition in MODULE_REGISTRY:
            with self.subTest(module=definition.key):
                self.assertIsNotNone(definition.readiness)

    def test_effectivity_and_utilization_remain_discovery_required(self):
        from backend.models import ModuleReadiness
        from backend.rbac.registry import MODULE_REGISTRY

        definitions = {definition.key: definition for definition in MODULE_REGISTRY}
        # These passthrough/hash-only handlers must not be silently presented as ready.
        self.assertEqual(definitions["effectivity"].readiness, ModuleReadiness.discovery_required)
        self.assertEqual(definitions["utilization"].readiness, ModuleReadiness.discovery_required)

    def test_available_set_is_explicit(self):
        from backend.models import ModuleReadiness
        from backend.rbac.registry import MODULE_REGISTRY

        available = {
            definition.key
            for definition in MODULE_REGISTRY
            if definition.readiness is ModuleReadiness.available
        }
        self.assertEqual(
            available,
            {"crew_hours", "admin_users", "admin_audit", "admin_settings"},
        )

    def test_readiness_syncs_to_db_and_api_payload(self):
        from backend.models import Module, ModuleReadiness
        from backend.tools.sync_registry import sync_registry

        self.app.create_user("viewer@example.test", roles=["viewer"])
        with self.app.database.SessionLocal() as session:
            effectivity = session.query(Module).filter(Module.key == "effectivity").one()
            self.assertEqual(effectivity.readiness, ModuleReadiness.discovery_required)
            effectivity.readiness = ModuleReadiness.under_development
            session.commit()
            sync_registry(session)
            effectivity = session.query(Module).filter(Module.key == "effectivity").one()
            self.assertEqual(effectivity.readiness, ModuleReadiness.discovery_required)

        response = self.app.client.get(
            "/api/modules",
            headers=self.app.headers("viewer@example.test"),
        )
        self.assertEqual(response.status_code, 200)
        payload = {module["key"]: module for module in response.json()}
        self.assertEqual(payload["effectivity"]["readiness"], "discovery_required")

    def test_readiness_does_not_affect_visibility(self):
        from backend.models import Module, ModuleReadiness, ModuleStatus

        self.app.create_user("viewer@example.test", roles=["viewer"])
        with self.app.database.SessionLocal() as session:
            effectivity = session.query(Module).filter(Module.key == "effectivity").one()
            self.assertEqual(effectivity.module_status, ModuleStatus.active)
            self.assertEqual(effectivity.readiness, ModuleReadiness.discovery_required)

        response = self.app.client.get(
            "/api/modules",
            headers=self.app.headers("viewer@example.test"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("effectivity", {module["key"] for module in response.json()})

    def test_tcm_indexing_is_registry_and_api_listed_without_a_route(self):
        from backend.models import ModuleReadiness
        from backend.rbac.registry import MODULE_REGISTRY

        definition = next(module for module in MODULE_REGISTRY if module.key == "tcm_indexing")
        self.assertIsNone(definition.route)
        self.assertEqual(definition.readiness, ModuleReadiness.not_migrated)

        self.app.create_user("viewer@example.test", roles=["viewer"])
        response = self.app.client.get(
            "/api/modules",
            headers=self.app.headers("viewer@example.test"),
        )
        self.assertEqual(response.status_code, 200)
        payload = {module["key"]: module for module in response.json()}
        self.assertIn("tcm_indexing", payload)
        self.assertIsNone(payload["tcm_indexing"]["route"])

    def test_admin_module_permissions_reuse_existing_admin_keys(self):
        from backend.models import BusinessArea
        from backend.rbac.registry import ADMIN_PERMISSION_KEYS, MODULE_REGISTRY

        admin_permissions = {
            module.required_view_permission
            for module in MODULE_REGISTRY
            if module.business_area is BusinessArea.admin
        }
        self.assertTrue(admin_permissions <= set(ADMIN_PERMISSION_KEYS))


if __name__ == "__main__":
    unittest.main()
