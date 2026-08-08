import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_PASSWORD = "BOOTSTRAP_TEST_ONLY_PASSWORD_123"


class TestBootstrapAdmin(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="bootstrap_admin_"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _database(self, name="bootstrap.db"):
        return self.tmpdir / name

    def _environment(self, database, *, password=TEST_PASSWORD):
        environment = os.environ.copy()
        environment["APP_ENV"] = "test"
        environment["DATABASE_URL"] = f"sqlite:///{database}"
        environment["JWT_SECRET_KEY"] = "BOOTSTRAP_TEST_ONLY_JWT_SECRET_32_BYTES"
        for variable in ("SQL_SERVER_HOST", "SQL_SERVER_USER", "SQL_SERVER_PASSWORD"):
            environment.pop(variable, None)
        environment.pop("BOOTSTRAP_ADMIN_EMAIL", None)
        if password is None:
            environment.pop("BOOTSTRAP_ADMIN_PASSWORD", None)
        else:
            environment["BOOTSTRAP_ADMIN_PASSWORD"] = password
        return environment

    def _run_python(self, script, database):
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            env=self._environment(database),
            capture_output=True,
            text=True,
            check=False,
        )
        return completed

    def _create_schema(self, database):
        script = """
import os
from sqlalchemy import create_engine
from backend.database import Base
import backend.models
engine = create_engine(os.environ["DATABASE_URL"])
Base.metadata.create_all(bind=engine)
engine.dispose()
"""
        completed = self._run_python(script, database)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def _run_cli(self, database, *, email="bootstrap-admin@example.test", password=TEST_PASSWORD, stdin=None):
        environment = self._environment(database, password=password)
        arguments = [sys.executable, "-m", "backend.tools.bootstrap_admin"]
        if email is not None:
            arguments.extend(("--email", email))
        return subprocess.run(
            arguments,
            cwd=PROJECT_ROOT,
            env=environment,
            stdin=stdin,
            capture_output=True,
            text=True,
            check=False,
        )

    def _user_and_role_rows(self, database):
        with sqlite3.connect(database) as connection:
            users = connection.execute(
                "SELECT id, email, hashed_password FROM users ORDER BY email"
            ).fetchall()
            roles = connection.execute(
                "SELECT user_id, role FROM user_roles ORDER BY user_id"
            ).fetchall()
        return users, roles

    def test_startup_does_not_create_user_or_role_on_empty_database(self):
        database = self._database("startup.db")
        completed = self._run_python(
            """
import json
import backend.database as database
import backend.main as main
main.startup_db_seed()
with database.SessionLocal() as session:
    from backend.models import Module, User, UserRole
    result = {
        "users": session.query(User).count(),
        "roles": session.query(UserRole).count(),
        "modules": session.query(Module).count(),
    }
print(json.dumps(result, sort_keys=True))
""",
            database,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout.strip().splitlines()[-1]), {
            "users": 0,
            "roles": 0,
            "modules": 9,
        })

    def test_cli_creates_one_super_admin_with_hashed_password(self):
        database = self._database()
        self._create_schema(database)

        completed = self._run_cli(database)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("bootstrap-admin@example.test", completed.stdout)
        self.assertNotIn(TEST_PASSWORD, completed.stdout + completed.stderr)
        users, roles = self._user_and_role_rows(database)
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0][1], "bootstrap-admin@example.test")
        self.assertNotEqual(users[0][2], TEST_PASSWORD)
        self.assertTrue(users[0][2])
        self.assertEqual(roles, [(users[0][0], "super_admin")])

    def test_cli_refuses_existing_super_admin_without_database_mutation(self):
        database = self._database()
        self._create_schema(database)
        first = self._run_cli(database, email="existing-admin@example.test")
        self.assertEqual(first.returncode, 0, first.stderr)
        before_hash = hashlib.sha256(database.read_bytes()).hexdigest()

        refused = self._run_cli(database, email="second-admin@example.test")

        self.assertEqual(refused.returncode, 1)
        self.assertIn("super admin already exists", refused.stderr)
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before_hash)
        users, roles = self._user_and_role_rows(database)
        self.assertEqual(len(users), 1)
        self.assertEqual(len(roles), 1)

    def test_cli_refuses_existing_email_without_database_mutation(self):
        database = self._database()
        self._create_schema(database)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "INSERT INTO users (id, email, hashed_password) VALUES (?, ?, ?)",
                ("existing-user", "existing-user@example.test", "existing-test-hash"),
            )
            connection.commit()
        before_hash = hashlib.sha256(database.read_bytes()).hexdigest()

        refused = self._run_cli(database, email="existing-user@example.test")

        self.assertEqual(refused.returncode, 1)
        self.assertIn("existing-user@example.test", refused.stderr)
        self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), before_hash)
        users, roles = self._user_and_role_rows(database)
        self.assertEqual(len(users), 1)
        self.assertEqual(roles, [])

    def test_cli_refuses_short_password(self):
        database = self._database()
        self._create_schema(database)

        refused = self._run_cli(database, password="TEST_ONLY")

        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("12", refused.stderr)
        self.assertEqual(self._user_and_role_rows(database), ([], []))

    def test_cli_refuses_without_password_or_tty(self):
        database = self._database()
        self._create_schema(database)

        refused = self._run_cli(database, password=None, stdin=subprocess.PIPE)

        self.assertNotEqual(refused.returncode, 0)
        self.assertIn("no interactive TTY", refused.stderr)
        self.assertEqual(self._user_and_role_rows(database), ([], []))


if __name__ == "__main__":
    unittest.main()
