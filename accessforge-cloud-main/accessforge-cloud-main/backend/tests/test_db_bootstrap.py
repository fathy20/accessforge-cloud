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
from unittest import mock

from backend.tools import db_bootstrap


PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TABLES = {
    "alembic_version",
    "audit_log",
    "jobs",
    "module_access",
    "modules",
    "notifications",
    "permissions",
    "projects",
    "role_permissions",
    "uploads",
    "user_invitations",
    "user_roles",
    "users",
}


class TestDbBootstrap(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="db_bootstrap_"))
        self.fallback_path = self.tmpdir / "application-fallback.db"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _path(self, name="target.db"):
        return self.tmpdir / name

    def _run_cli(self, *arguments):
        env = os.environ.copy()
        # Proves the CLI target, not an application fallback URL, selects the DB.
        env["DATABASE_URL"] = f"sqlite:///{self.fallback_path}"
        completed = subprocess.run(
            [sys.executable, "-m", "backend.tools.db_bootstrap", *map(str, arguments)],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed, json.loads(completed.stdout)

    def _sqlite_tables(self, path):
        connection = sqlite3.connect(path)
        try:
            return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            connection.close()

    def _create_metadata_database(self, path):
        script = """
from sqlalchemy import create_engine
from backend.database import Base
import backend.models
engine = create_engine(r'__URL__')
Base.metadata.create_all(bind=engine)
engine.dispose()
""".replace("__URL__", f"sqlite:///{path}")
        env = os.environ.copy()
        env["DATABASE_URL"] = "sqlite:///:memory:"
        completed = subprocess.run(
            [sys.executable, "-c", script], cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_missing_path_bootstraps_through_alembic_without_seed_data(self):
        path = self._path()

        completed, result = self._run_cli("--database", path)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["status"], "created")
        self.assertTrue(result["migrations_applied"])
        self.assertEqual(result["final_revision"], "f7a8b9c0d1e2")
        self.assertEqual(self._sqlite_tables(path), EXPECTED_TABLES)
        self.assertFalse(self.fallback_path.exists())
        connection = sqlite3.connect(path)
        try:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
        finally:
            connection.close()

    def test_existing_zero_byte_file_bootstraps(self):
        path = self._path()
        path.write_bytes(b"")

        completed, result = self._run_cli("--database", path)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["database_state"], "empty_file")
        self.assertEqual(result["status"], "created")

    def test_existing_database_with_no_tables_bootstraps(self):
        path = self._path()
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA user_version = 1")
            connection.commit()
        finally:
            connection.close()

        completed, result = self._run_cli("--url", f"sqlite:///{path}")

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["database_state"], "no_user_tables")
        self.assertEqual(result["status"], "created")

    def test_already_current_database_is_unchanged(self):
        path = self._path()
        first, _ = self._run_cli("--database", path)
        self.assertEqual(first.returncode, 0, first.stderr)
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        before_mtime = path.stat().st_mtime_ns

        completed, result = self._run_cli("--database", path)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["status"], "already_current")
        self.assertFalse(result["migrations_applied"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(path.stat().st_mtime_ns, before_mtime)

    def test_non_alembic_schema_is_refused_without_change(self):
        path = self._path()
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE legacy_data (id INTEGER PRIMARY KEY, value TEXT)")
            connection.commit()
        finally:
            connection.close()
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        completed, result = self._run_cli("--database", path)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["database_state"], "non_alembic_schema")
        self.assertIn("parity/adoption", result["message"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before_hash)

    def test_metadata_created_schema_is_refused_without_change(self):
        path = self._path()
        self._create_metadata_database(path)
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        completed, result = self._run_cli("--database", path)

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["database_state"], "non_alembic_schema")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before_hash)

    def test_unknown_alembic_revision_is_refused_even_with_upgrade_flag(self):
        path = self._path()
        connection = sqlite3.connect(path)
        try:
            connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
            connection.execute("INSERT INTO alembic_version (version_num) VALUES ('unknown_revision')")
            connection.commit()
        finally:
            connection.close()
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        completed, result = self._run_cli("--database", path, "--upgrade-existing")

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(result["status"], "refused")
        self.assertEqual(result["database_state"], "incompatible")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before_hash)

    def test_controlled_known_behind_state_requires_flag_then_upgrades(self):
        path = self._path()
        connection = sqlite3.connect(path)
        try:
            connection.execute("PRAGMA user_version = 1")
            connection.commit()
        finally:
            connection.close()
        target_url = f"sqlite:///{path.as_posix()}"
        config, _, head = db_bootstrap._alembic_config(target_url)
        with mock.patch.object(db_bootstrap, "_inspect_existing", return_value=("behind_head", "previous_revision", None)), \
             mock.patch.object(db_bootstrap, "_run_upgrade") as upgrade, \
             mock.patch.object(db_bootstrap, "_current_revision", return_value=head), \
             mock.patch.object(db_bootstrap, "_parity_message", return_value=(True, "Schema matches current SQLAlchemy metadata.")):
            refused = db_bootstrap.bootstrap_sqlite(str(path))
            upgraded = db_bootstrap.bootstrap_sqlite(str(path), upgrade_existing=True)

        self.assertEqual(refused.status, "refused")
        self.assertEqual(upgraded.status, "upgraded")
        upgrade.assert_called_once()
        self.assertEqual(upgrade.call_args.args[1], target_url)

    def test_invalid_sqlite_file_is_not_changed(self):
        path = self._path()
        path.write_bytes(b"not a sqlite database")
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()

        completed, result = self._run_cli("--database", path)

        self.assertEqual(completed.returncode, 3)
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["database_state"], "invalid")
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before_hash)

    def test_missing_parent_and_relative_path_are_refused_without_creation(self):
        missing_parent_target = self.tmpdir / "missing" / "target.db"
        missing_parent, missing_parent_result = self._run_cli("--database", missing_parent_target)
        relative, relative_result = self._run_cli("--database", "relative.db")

        self.assertEqual(missing_parent.returncode, 3)
        self.assertIn("parent directory", missing_parent_result["message"])
        self.assertFalse(missing_parent_target.parent.exists())
        self.assertEqual(relative.returncode, 3)
        self.assertIn("absolute path", relative_result["message"])

    def test_non_sqlite_url_and_redsea_name_are_refused(self):
        non_sqlite, non_sqlite_result = self._run_cli("--url", "postgresql://example.invalid/redsea")
        redsea_path = self._path("redsea.db")
        redsea_path.write_bytes(b"")
        redsea, redsea_result = self._run_cli("--database", redsea_path)

        self.assertEqual(non_sqlite.returncode, 3)
        self.assertIn("Only SQLite", non_sqlite_result["message"])
        self.assertEqual(redsea.returncode, 3)
        self.assertIn("refused", redsea_result["message"])
        self.assertEqual(redsea_path.read_bytes(), b"")

    def test_fresh_bootstrap_matches_parity_checker(self):
        path = self._path()
        created, _ = self._run_cli("--database", path)
        self.assertEqual(created.returncode, 0, created.stderr)
        completed = subprocess.run(
            [sys.executable, "-m", "backend.tools.schema_parity", "--database", str(path)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["decision"], "safe_to_stamp")

    def test_bootstrap_source_has_no_runtime_ddl_or_main_import(self):
        source = (PROJECT_ROOT / "backend" / "tools" / "db_bootstrap.py").read_text(encoding="utf-8")

        self.assertNotIn("backend.main", source)
        self.assertNotIn("create_all(", source)
        self.assertNotIn("ALTER TABLE", source)
        self.assertNotIn("command.stamp", source)
        self.assertNotIn("command.downgrade", source)


if __name__ == "__main__":
    unittest.main()
