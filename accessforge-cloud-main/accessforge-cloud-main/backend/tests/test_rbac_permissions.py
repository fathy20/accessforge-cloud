import os
import shutil
import sys
import tempfile
import unittest

from fastapi.testclient import TestClient


class AppHarness:
    """Fresh file-backed SQLite application for one isolated test case."""

    def __init__(self):
        self.tmpdir = tempfile.mkdtemp(prefix="rbac_foundation_")
        self.database_path = os.path.join(self.tmpdir, "app.sqlite")
        self.original_env = {
            name: os.environ.get(name)
            for name in ("APP_ENV", "DATABASE_URL", "JWT_SECRET_KEY")
        }
        os.environ["APP_ENV"] = "test"
        os.environ["DATABASE_URL"] = f"sqlite:///{self.database_path.replace(os.sep, '/')}"
        os.environ["JWT_SECRET_KEY"] = "RBAC_FOUNDATION_TEST_JWT_SECRET_32_BYTES"
        self._clear_backend_modules()

        import backend.database as database
        import backend.main as main

        self.database = database
        self.main = main
        self.client_context = TestClient(main.app)
        self.client = self.client_context.__enter__()

    @staticmethod
    def _clear_backend_modules():
        for name in list(sys.modules):
            if name == "backend" or (
                name.startswith("backend.") and not name.startswith("backend.tests")
            ):
                sys.modules.pop(name, None)

    def close(self):
        self.client_context.__exit__(None, None, None)
        self.database.engine.dispose()
        self._clear_backend_modules()
        for name, value in self.original_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def create_user(self, email, roles=(), password="RBAC_TEST_PASSWORD_123", status=None):
        from backend.auth import get_password_hash
        from backend.models import AppRole, User, UserRole, UserStatus

        with self.database.SessionLocal() as session:
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                full_name=email.split("@", 1)[0],
                status=status or UserStatus.active,
            )
            session.add(user)
            session.flush()
            for role in roles:
                session.add(UserRole(user_id=user.id, role=AppRole(role)))
            session.commit()
            return user.id

    def user_id(self, email):
        from backend.models import User

        with self.database.SessionLocal() as session:
            return session.query(User.id).filter(User.email == email).scalar()

    def login(self, email, password="RBAC_TEST_PASSWORD_123"):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def headers(self, email, password="RBAC_TEST_PASSWORD_123"):
        response = self.login(email, password)
        response.raise_for_status()
        return {"Authorization": f"Bearer {response.json()['access_token']}"}


class TestRbacPermissions(unittest.TestCase):
    def setUp(self):
        self.app = AppHarness()

    def tearDown(self):
        self.app.close()

    def test_default_deny_guest_has_no_permissions_or_modules(self):
        self.app.create_user("guest@example.test", roles=["guest"])
        from backend.rbac.permissions import get_effective_permissions
        from backend.models import User

        with self.app.database.SessionLocal() as session:
            guest = session.query(User).filter(User.email == "guest@example.test").one()
            self.assertEqual(get_effective_permissions(session, guest), set())

        response = self.app.client.get(
            "/api/modules", headers=self.app.headers("guest@example.test")
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

    def test_role_permission_matrix_is_explicit_and_exact(self):
        from backend.rbac.permissions import get_effective_permissions
        from backend.rbac.registry import PERMISSION_KEYS, expected_role_permissions
        from backend.models import AppRole, User

        expected = expected_role_permissions(PERMISSION_KEYS)
        for role in ("super_admin", "admin", "engineer", "viewer", "guest"):
            email = f"{role}@example.test"
            self.app.create_user(email, roles=[role])
            with self.app.database.SessionLocal() as session:
                user = session.query(User).filter(User.email == email).one()
                actual = get_effective_permissions(session, user)
            self.assertEqual(actual, expected[AppRole(role)])

        self.assertIn("admin.users.view", expected[AppRole.admin])
        self.assertNotIn("admin.users.view", expected[AppRole.engineer])
        self.assertNotIn("check_control.export", expected[AppRole.viewer])

    def test_sync_is_idempotent_and_does_not_create_users_or_user_roles(self):
        from backend.models import Module, Permission, RolePermission, User, UserRole
        from backend.tools.sync_registry import sync_registry

        with self.app.database.SessionLocal() as session:
            before = (
                session.query(Module).count(),
                session.query(Permission).count(),
                session.query(RolePermission).count(),
                session.query(User).count(),
                session.query(UserRole).count(),
            )
            sync_registry(session)
            middle = (
                session.query(Module).count(),
                session.query(Permission).count(),
                session.query(RolePermission).count(),
                session.query(User).count(),
                session.query(UserRole).count(),
            )
            sync_registry(session)
            after = (
                session.query(Module).count(),
                session.query(Permission).count(),
                session.query(RolePermission).count(),
                session.query(User).count(),
                session.query(UserRole).count(),
            )

        self.assertEqual(before, (13, 19, 60, 0, 0))
        self.assertEqual(middle, before)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
