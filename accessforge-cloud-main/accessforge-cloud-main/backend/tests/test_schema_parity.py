import hashlib
import os
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.database import Base
import backend.models  # noqa: F401
from backend.tools.schema_parity import (
    EXIT_COMPATIBLE,
    EXIT_ERROR,
    check_sqlite_schema,
    main,
)


class TestSchemaParity(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="schema_parity_"))

    def tearDown(self):
        for path in self.tmpdir.iterdir():
            path.unlink()
        self.tmpdir.rmdir()

    def _db_path(self, name="target.db"):
        return self.tmpdir / name

    def _engine(self, path):
        return create_engine(f"sqlite:///{path}")

    def _create_metadata_database(self, path, exclude=()):
        engine = self._engine(path)
        try:
            excluded = set(exclude)
            tables = [table for table in Base.metadata.sorted_tables if table.name not in excluded]
            Base.metadata.create_all(bind=engine, tables=tables)
        finally:
            engine.dispose()

    def _categories(self, result):
        return {difference.category for difference in result.differences}

    def test_metadata_database_is_safe_to_stamp_and_unchanged(self):
        path = self._db_path()
        self._create_metadata_database(path)
        before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
        before_mtime = path.stat().st_mtime_ns

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "compatible")
        self.assertEqual(result.decision, "safe_to_stamp")
        self.assertTrue(result.summary["read_only_hash_unchanged"])
        self.assertTrue(result.summary["read_only_mtime_unchanged"])
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before_hash)
        self.assertEqual(path.stat().st_mtime_ns, before_mtime)
        connection = sqlite3.connect(path)
        try:
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        finally:
            connection.close()
        self.assertNotIn("alembic_version", tables)

    def test_baseline_migrated_database_is_safe_to_stamp(self):
        path = self._db_path("baseline.db")
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{path}"
        completed = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        result = check_sqlite_schema(f"sqlite:///{path}")

        self.assertEqual(result.status, "compatible")
        self.assertEqual(result.decision, "safe_to_stamp")

    def test_unknown_alembic_revision_is_incompatible(self):
        path = self._db_path()
        self._create_metadata_database(path)
        engine = self._engine(path)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
                connection.execute(text("INSERT INTO alembic_version (version_num) VALUES ('unknown_revision')"))
        finally:
            engine.dispose()

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "incompatible")
        self.assertEqual(result.decision, "incompatible")
        self.assertIn("alembic_revision", self._categories(result))
    def test_missing_table_is_incompatible(self):
        path = self._db_path()
        self._create_metadata_database(path, exclude={"notifications"})

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "incompatible")
        self.assertEqual(result.decision, "incompatible")
        self.assertIn("table", self._categories(result))

    def test_missing_column_is_incompatible(self):
        path = self._db_path()
        self._create_metadata_database(path, exclude={"users"})
        engine = self._engine(path)
        try:
            with engine.begin() as connection:
                connection.execute(text("""
                    CREATE TABLE users (
                        id VARCHAR(36) NOT NULL,
                        email VARCHAR(255),
                        hashed_password VARCHAR(255),
                        full_name VARCHAR(255),
                        avatar_url VARCHAR(512),
                        department VARCHAR(255),
                        job_title VARCHAR(255),
                        employee_id VARCHAR(64),
                        status VARCHAR(32),
                        last_seen_at DATETIME,
                        created_at DATETIME,
                        updated_at DATETIME,
                        CONSTRAINT pk_users PRIMARY KEY (id)
                    )
                """))
                connection.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
        finally:
            engine.dispose()

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "incompatible")
        self.assertTrue(any(d.object_name == "users.phone" for d in result.differences))

    def test_extra_table_requires_repair_decision(self):
        path = self._db_path()
        self._create_metadata_database(path)
        engine = self._engine(path)
        try:
            with engine.begin() as connection:
                connection.execute(text("CREATE TABLE legacy_notes (id INTEGER PRIMARY KEY, note TEXT)"))
        finally:
            engine.dispose()

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "incompatible")
        self.assertEqual(result.decision, "repair_required")
        self.assertIn("extra_table", self._categories(result))

    def test_nullable_mismatch_is_incompatible(self):
        path = self._db_path()
        self._create_metadata_database(path, exclude={"modules"})
        engine = self._engine(path)
        try:
            with engine.begin() as connection:
                connection.execute(text("""
                    CREATE TABLE modules (
                        id VARCHAR(36) NOT NULL,
                        key VARCHAR(128),
                        name VARCHAR(255) NOT NULL,
                        description VARCHAR(1024),
                        icon VARCHAR(128),
                        category VARCHAR(128),
                        enabled BOOLEAN,
                        sort_order INTEGER,
                        CONSTRAINT pk_modules PRIMARY KEY (id)
                    )
                """))
                connection.execute(text("CREATE UNIQUE INDEX ix_modules_key ON modules (key)"))
        finally:
            engine.dispose()

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "incompatible")
        self.assertTrue(any(d.category == "nullable" and d.object_name == "modules.name" for d in result.differences))

    def test_index_mismatch_is_incompatible(self):
        path = self._db_path()
        self._create_metadata_database(path)
        engine = self._engine(path)
        try:
            with engine.begin() as connection:
                connection.execute(text("DROP INDEX ix_modules_key"))
        finally:
            engine.dispose()

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "incompatible")
        self.assertIn("index", self._categories(result))

    def test_foreign_key_mismatch_is_incompatible(self):
        path = self._db_path()
        self._create_metadata_database(path, exclude={"user_roles"})
        engine = self._engine(path)
        try:
            with engine.begin() as connection:
                connection.execute(text("""
                    CREATE TABLE user_roles (
                        id VARCHAR(36) NOT NULL,
                        user_id VARCHAR(36),
                        role VARCHAR(11),
                        CONSTRAINT fk_user_roles_user_id_modules FOREIGN KEY (user_id) REFERENCES modules (id),
                        CONSTRAINT pk_user_roles PRIMARY KEY (id)
                    )
                """))
        finally:
            engine.dispose()

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "incompatible")
        self.assertIn("foreign_key", self._categories(result))

    def test_empty_database_is_incompatible(self):
        path = self._db_path()
        sqlite3.connect(path).close()

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "incompatible")
        self.assertEqual(result.decision, "incompatible")
        self.assertIn("table", self._categories(result))

    def test_missing_path_is_refused_without_file_creation(self):
        path = self._db_path("does-not-exist.db")

        result = check_sqlite_schema(str(path))

        self.assertEqual(result.status, "error")
        self.assertFalse(path.exists())
        self.assertEqual(main(["--database", str(path)]), EXIT_ERROR)
        self.assertFalse(path.exists())

    def test_non_sqlite_url_is_refused(self):
        result = check_sqlite_schema("postgresql://example.invalid/redsea")

        self.assertEqual(result.status, "error")
        self.assertIn("Only explicit SQLite", result.summary["error"])

    def test_cli_returns_compatible_exit_code(self):
        path = self._db_path()
        self._create_metadata_database(path)

        self.assertEqual(main(["--url", f"sqlite:///{path}"]), EXIT_COMPATIBLE)


if __name__ == "__main__":
    unittest.main()
