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


class TestRuntimeAlterRetirement(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp(prefix="runtime_alter_retirement_"))

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _run(self, script, database):
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{database}"
        env.pop("SQL_SERVER_HOST", None)
        env.pop("SQL_SERVER_USER", None)
        env.pop("SQL_SERVER_PASSWORD", None)
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        try:
            return json.loads(completed.stdout.strip().splitlines()[-1])
        except json.JSONDecodeError as exc:
            self.fail(f"subprocess did not return JSON: stdout={completed.stdout!r}; stderr={completed.stderr!r}; error={exc}")

    def _bootstrap(self, database):
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{self.tmpdir / 'fallback.db'}"
        completed = subprocess.run(
            [sys.executable, "-m", "backend.tools.db_bootstrap", "--database", str(database)],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def _columns(self, database, table):
        with sqlite3.connect(database) as connection:
            return [row[1] for row in connection.execute(f'PRAGMA table_info("{table}")')]

    def test_bootstrapped_startup_has_no_alter_and_seed_is_idempotent(self):
        database = self.tmpdir / "managed.db"
        self._bootstrap(database)
        result = self._run(
            """
import json
from sqlalchemy import event, inspect
import backend.database as database
statements = []
event.listen(database.engine, "before_cursor_execute", lambda conn, cursor, statement, params, context, executemany: statements.append(statement))
import backend.main as main
main.startup_db_seed()
main.startup_db_seed()
from backend.models import Module, User, UserRole
with database.SessionLocal() as session:
    counts = {
        "users": session.query(User).count(),
        "roles": session.query(UserRole).count(),
        "modules": session.query(Module).count(),
    }
schema = {
    table: [column["name"] for column in inspect(database.engine).get_columns(table)]
    for table in inspect(database.engine).get_table_names()
}
print(json.dumps({"alter": [s for s in statements if "alter table" in s.lower()], "counts": counts, "schema": schema}))
""",
            database,
        )
        self.assertEqual(result["alter"], [])
        self.assertEqual(result["counts"], {"users": 0, "roles": 0, "modules": 9})

    def test_outdated_users_fixture_is_not_repaired(self):
        database = self.tmpdir / "outdated.db"
        self._run(
            """
from sqlalchemy import create_engine
from backend.database import Base
import backend.models
engine = create_engine(__import__("os").environ["DATABASE_URL"])
Base.metadata.create_all(bind=engine)
engine.dispose()
import sqlite3
with sqlite3.connect(__import__("os").environ["DATABASE_URL"].removeprefix("sqlite:///")) as connection:
    connection.execute("ALTER TABLE users DROP COLUMN avatar_url")
print("{}")
""",
            database,
        )
        before = self._columns(database, "users")
        result = self._run(
            """
import json
from sqlalchemy import event
import backend.database as database
statements = []
event.listen(database.engine, "before_cursor_execute", lambda conn, cursor, statement, params, context, executemany: statements.append(statement))
import backend.main as main
try:
    main.startup_db_seed()
    startup = "succeeded"
except Exception as exc:
    startup = f"failed: {type(exc).__name__}"
print(json.dumps({"startup": startup, "alter": [s for s in statements if "alter table" in s.lower()]}))
""",
            database,
        )
        after = self._columns(database, "users")
        self.assertNotIn("avatar_url", before)
        self.assertNotIn("avatar_url", after)
        self.assertEqual(result["alter"], [])

    def test_runtime_source_keeps_create_all_and_tools_stay_independent(self):
        source = (PROJECT_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
        self.assertIn("Base.metadata.create_all(bind=engine)", source)
        self.assertNotIn("ALTER TABLE", source.upper())
        result = self._run(
            """
import importlib
import sys
for name in ("backend.tools.schema_parity", "backend.tools.db_bootstrap", "backend.tools.db_adopt"):
    importlib.import_module(name)
    assert "backend.main" not in sys.modules, name
print("{}")
""",
            self.tmpdir / "unused.db",
        )
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
