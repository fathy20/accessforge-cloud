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

from backend.tools import db_adopt


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BASELINE = "e1a2b3c4d5f6"


class TestDbAdopt(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="db_adopt_"))
        self.fallback_path = self.tmpdir / "application-fallback.db"

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _path(self, name="source.db"):
        return self.tmpdir / name

    def _create_compatible_source(self, path):
        script = """
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database import Base
from backend.models import Module, User
engine = create_engine(r'__URL__')
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
with Session() as session:
    session.add(User(id='user-1', email='adoption@example.test', full_name='Adoption User'))
    session.add(Module(id='module-1', key='check_control', name='Check Control'))
    session.commit()
engine.dispose()
""".replace("__URL__", f"sqlite:///{path}")
        environment = os.environ.copy()
        environment["DATABASE_URL"] = "sqlite:///:memory:"
        completed = subprocess.run(
            [sys.executable, "-c", script], cwd=PROJECT_ROOT, env=environment, capture_output=True, text=True, check=False
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def _run_cli(self, *arguments):
        environment = os.environ.copy()
        environment["DATABASE_URL"] = f"sqlite:///{self.fallback_path}"
        completed = subprocess.run(
            [sys.executable, "-m", "backend.tools.db_adopt", *map(str, arguments)],
            cwd=PROJECT_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed, json.loads(completed.stdout)

    def _revision(self, path):
        connection = sqlite3.connect(path)
        try:
            return connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        finally:
            connection.close()

    def _user_rows(self, path):
        connection = sqlite3.connect(path)
        try:
            return connection.execute("SELECT id, email, full_name FROM users ORDER BY id").fetchall()
        finally:
            connection.close()

    def test_compatible_non_alembic_database_is_backed_up_and_adopted(self):
        source = self._path()
        backup = self._path("source.before-adoption.db")
        self._create_compatible_source(source)
        before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        before_rows = self._user_rows(source)

        completed, result = self._run_cli("--database", source, "--backup", backup, "--confirm-stamp", BASELINE)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["status"], "adopted")
        self.assertEqual(result["parity_decision"], "safe_to_stamp")
        self.assertEqual(result["final_revision"], BASELINE)
        self.assertEqual(result["source_hash_before"], before_hash)
        self.assertTrue(backup.exists())
        self.assertEqual(hashlib.sha256(backup.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(result["backup_hash"], before_hash)
        self.assertEqual(self._revision(source), BASELINE)
        self.assertEqual(self._user_rows(source), before_rows)
        self.assertFalse(self.fallback_path.exists())

    def test_missing_or_wrong_confirmation_refuses_without_backup(self):
        source = self._path()
        self._create_compatible_source(source)
        before_hash = hashlib.sha256(source.read_bytes()).hexdigest()
        missing_backup = self._path("missing-confirmation.backup.db")
        wrong_backup = self._path("wrong-confirmation.backup.db")

        missing, missing_result = self._run_cli("--database", source, "--backup", missing_backup)
        wrong, wrong_result = self._run_cli("--database", source, "--backup", wrong_backup, "--confirm-stamp", "wrong")

        self.assertEqual(missing.returncode, 1)
        self.assertEqual(wrong.returncode, 1)
        self.assertEqual(missing_result["status"], "refused")
        self.assertEqual(wrong_result["status"], "refused")
        self.assertFalse(missing_backup.exists())
        self.assertFalse(wrong_backup.exists())
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before_hash)

    def test_backup_validation_refuses_missing_existing_and_missing_parent(self):
        source = self._path()
        self._create_compatible_source(source)
        existing_backup = self._path("existing.backup.db")
        existing_backup.write_bytes(b"keep")
        missing_parent_backup = self.tmpdir / "missing" / "backup.db"

        missing, missing_result = self._run_cli("--database", source, "--confirm-stamp", BASELINE)
        existing, existing_result = self._run_cli("--database", source, "--backup", existing_backup, "--confirm-stamp", BASELINE)
        missing_parent, missing_parent_result = self._run_cli("--database", source, "--backup", missing_parent_backup, "--confirm-stamp", BASELINE)

        self.assertEqual(missing.returncode, 1)
        self.assertIn("backup path", missing_result["message"])
        self.assertEqual(existing.returncode, 1)
        self.assertEqual(existing_backup.read_bytes(), b"keep")
        self.assertEqual(missing_parent.returncode, 1)
        self.assertIn("parent", missing_parent_result["message"])
        self.assertFalse(missing_parent_backup.parent.exists())

    def test_incompatible_and_repair_required_schemas_are_refused_before_backup(self):
        incompatible = self._path("incompatible.db")
        sqlite3.connect(incompatible).close()
        compatible = self._path("repair-required.db")
        self._create_compatible_source(compatible)
        connection = sqlite3.connect(compatible)
        try:
            connection.execute("CREATE TABLE legacy_notes (id INTEGER PRIMARY KEY, value TEXT)")
            connection.commit()
        finally:
            connection.close()
        incompatible_backup = self._path("incompatible.backup.db")
        repair_backup = self._path("repair.backup.db")

        first, first_result = self._run_cli("--database", incompatible, "--backup", incompatible_backup, "--confirm-stamp", BASELINE)
        second, second_result = self._run_cli("--database", compatible, "--backup", repair_backup, "--confirm-stamp", BASELINE)

        self.assertEqual(first.returncode, 1)
        self.assertEqual(first_result["parity_decision"], "incompatible")
        self.assertEqual(second.returncode, 1)
        self.assertEqual(second_result["parity_decision"], "repair_required")
        self.assertFalse(incompatible_backup.exists())
        self.assertFalse(repair_backup.exists())

    def test_unverifiable_parity_is_refused_without_backup(self):
        source = self._path()
        self._create_compatible_source(source)
        backup = self._path("unverifiable.backup.db")
        with mock.patch.object(db_adopt, "_run_parity", return_value=("unverifiable", [], None)):
            result = db_adopt.adopt_sqlite(str(source), str(backup), BASELINE)

        self.assertEqual(result.status, "refused")
        self.assertFalse(backup.exists())

    def test_already_adopted_returns_without_backup_or_confirmation(self):
        source = self._path()
        backup = self._path("unused.backup.db")
        self._create_compatible_source(source)
        adopted, adopted_result = self._run_cli("--database", source, "--backup", backup, "--confirm-stamp", BASELINE)
        self.assertEqual(adopted.returncode, 0, adopted.stderr)
        self.assertEqual(adopted_result["status"], "adopted")
        before_hash = hashlib.sha256(source.read_bytes()).hexdigest()

        completed, result = self._run_cli("--database", source)

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(result["status"], "already_adopted")
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before_hash)

    def test_unknown_revision_invalid_and_missing_source_are_not_modified(self):
        unknown = self._path("unknown.db")
        self._create_compatible_source(unknown)
        connection = sqlite3.connect(unknown)
        try:
            connection.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
            connection.execute("INSERT INTO alembic_version (version_num) VALUES ('unknown_revision')")
            connection.commit()
        finally:
            connection.close()
        unknown_hash = hashlib.sha256(unknown.read_bytes()).hexdigest()
        invalid = self._path("invalid.db")
        invalid.write_bytes(b"not sqlite")
        invalid_hash = hashlib.sha256(invalid.read_bytes()).hexdigest()
        missing = self._path("missing.db")

        unknown_run, unknown_result = self._run_cli("--database", unknown, "--backup", self._path("unknown.backup.db"), "--confirm-stamp", BASELINE)
        invalid_run, invalid_result = self._run_cli("--database", invalid, "--backup", self._path("invalid.backup.db"), "--confirm-stamp", BASELINE)
        missing_run, missing_result = self._run_cli("--database", missing, "--backup", self._path("missing.backup.db"), "--confirm-stamp", BASELINE)

        self.assertEqual(unknown_run.returncode, 1)
        self.assertEqual(unknown_result["status"], "refused")
        self.assertEqual(hashlib.sha256(unknown.read_bytes()).hexdigest(), unknown_hash)
        self.assertEqual(invalid_run.returncode, 3)
        self.assertEqual(invalid_result["status"], "error")
        self.assertEqual(hashlib.sha256(invalid.read_bytes()).hexdigest(), invalid_hash)
        self.assertEqual(missing_run.returncode, 1)
        self.assertEqual(missing_result["status"], "refused")
        self.assertFalse(missing.exists())

    def test_non_sqlite_and_redsea_name_are_refused(self):
        non_sqlite, non_sqlite_result = self._run_cli("--url", "postgresql://example.invalid/redsea")
        redsea = self._path("redsea.db")
        redsea.write_bytes(b"")
        redsea_run, redsea_result = self._run_cli("--database", redsea)

        self.assertEqual(non_sqlite.returncode, 3)
        self.assertEqual(non_sqlite_result["status"], "error")
        self.assertEqual(redsea_run.returncode, 3)
        self.assertIn("refused", redsea_result["message"])
        self.assertEqual(redsea.read_bytes(), b"")

    def test_backup_failure_and_stamp_failure_preserve_recovery_artifacts(self):
        source = self._path()
        self._create_compatible_source(source)
        backup_failure = self._path("backup-failure.db")
        with mock.patch.object(db_adopt.shutil, "copyfile", side_effect=OSError("simulated backup failure")):
            backup_result = db_adopt.adopt_sqlite(str(source), str(backup_failure), BASELINE)
        self.assertEqual(backup_result.status, "backup_failed")
        self.assertFalse(backup_failure.exists())

        stamp_backup = self._path("stamp-failure.db")
        with mock.patch.object(db_adopt, "_stamp", side_effect=RuntimeError("simulated stamp failure")):
            stamp_result = db_adopt.adopt_sqlite(str(source), str(stamp_backup), BASELINE)
        self.assertEqual(stamp_result.status, "stamp_failed")
        self.assertTrue(stamp_backup.exists())
        self.assertIn("Restore the verified backup manually", stamp_result.message)
        connection = sqlite3.connect(source)
        try:
            self.assertNotIn("alembic_version", {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")})
        finally:
            connection.close()

    def test_verification_failure_reports_manual_recovery(self):
        source = self._path()
        backup = self._path("verification-failure.db")
        self._create_compatible_source(source)
        with mock.patch.object(
            db_adopt,
            "_run_parity",
            side_effect=[("safe_to_stamp", [], None), ("incompatible", [], None)],
        ):
            result = db_adopt.adopt_sqlite(str(source), str(backup), BASELINE)

        self.assertEqual(result.status, "verification_failed")
        self.assertTrue(backup.exists())
        self.assertIn("Restore the verified backup manually", result.message)
        self.assertEqual(self._revision(source), BASELINE)

    def test_adoption_source_has_no_runtime_ddl_or_main_import(self):
        source = (PROJECT_ROOT / "backend" / "tools" / "db_adopt.py").read_text(encoding="utf-8")

        self.assertNotIn("backend.main", source)
        self.assertNotIn("create_all(", source)
        self.assertNotIn("ALTER TABLE", source)
        self.assertNotIn("command.upgrade", source)
        self.assertNotIn("command.downgrade", source)


if __name__ == "__main__":
    unittest.main()
