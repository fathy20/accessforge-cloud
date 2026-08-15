from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient


# unittest does not load pytest conftest.py; keep its imports equally isolated.
os.environ["APP_ENV"] = "test"
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"


SQL_SERVER_URL = (
    "mssql+pyodbc:///?odbc_connect="
    "DRIVER%3D%7BODBC+Driver+18+for+SQL+Server%7D%3B"
    "SERVER%3Dlocal-test%3BDATABASE%3Dtest_db%3BTrusted_Connection%3Dyes%3B"
)


class TestDatabaseConfiguration(unittest.TestCase):
    def test_auto_schema_policy_allows_development_sqlite(self):
        from backend.config import should_auto_create_schema

        self.assertTrue(should_auto_create_schema("development", "sqlite"))

    def test_auto_schema_policy_allows_test_sqlite(self):
        from backend.config import should_auto_create_schema

        self.assertTrue(should_auto_create_schema("test", "sqlite"))

    def test_auto_schema_policy_rejects_production_sqlite(self):
        from backend.config import should_auto_create_schema

        self.assertFalse(should_auto_create_schema("production", "sqlite"))

    def test_auto_schema_policy_rejects_development_mssql(self):
        from backend.config import should_auto_create_schema

        self.assertFalse(should_auto_create_schema("development", "mssql"))

    def test_auto_schema_policy_rejects_test_mssql(self):
        from backend.config import should_auto_create_schema

        self.assertFalse(should_auto_create_schema("test", "mssql"))

    def test_auto_schema_policy_rejects_production_mssql(self):
        from backend.config import should_auto_create_schema

        self.assertFalse(should_auto_create_schema("production", "mssql"))

    def test_auto_schema_policy_rejects_other_and_unknown_dialects(self):
        from backend.config import should_auto_create_schema

        for dialect in ("postgresql", "mysql", "oracle", "unknown"):
            with self.subTest(dialect=dialect):
                self.assertFalse(should_auto_create_schema("development", dialect))

    def test_non_sqlite_engine_does_not_invoke_create_all(self):
        script = """
import json
from types import SimpleNamespace
from unittest.mock import patch

import backend.database as database

database.engine = SimpleNamespace(dialect=SimpleNamespace(name="mssql"))
with patch.object(database.Base.metadata, "create_all") as create_all:
    import backend.main

print(json.dumps({"called": create_all.call_count}))
"""
        environment = os.environ.copy()
        environment["APP_ENV"] = "development"
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout.strip()), {"called": 0})

    def test_production_requires_database_url(self):
        from backend.config import ConfigurationError, resolve_database_url

        with self.assertRaises(ConfigurationError) as captured:
            resolve_database_url("production", {})

        self.assertIn("DATABASE_URL", str(captured.exception))
        self.assertNotIn("local-test", str(captured.exception))

    def test_production_rejects_sqlite(self):
        from backend.config import ConfigurationError, resolve_database_url

        with self.assertRaises(ConfigurationError) as captured:
            resolve_database_url("production", {"DATABASE_URL": "sqlite:///:memory:"})

        self.assertIn("SQLite", str(captured.exception))
        self.assertNotIn(":memory:", str(captured.exception))

    def test_production_accepts_sql_server_url_without_connecting(self):
        from backend.config import resolve_database_url

        self.assertEqual(
            resolve_database_url("production", {"DATABASE_URL": SQL_SERVER_URL}),
            SQL_SERVER_URL,
        )

    def test_development_accepts_explicit_sql_server_url(self):
        from backend.config import resolve_database_url

        self.assertEqual(
            resolve_database_url("development", {"DATABASE_URL": SQL_SERVER_URL}),
            SQL_SERVER_URL,
        )

    def test_development_without_configuration_keeps_sqlite_default(self):
        from backend.config import DEFAULT_DATABASE_URL, resolve_database_url

        self.assertEqual(resolve_database_url("development", {}), DEFAULT_DATABASE_URL)

    def test_unknown_app_env_is_rejected_without_echoing_value(self):
        from backend.config import ConfigurationError, get_app_env

        with self.assertRaises(ConfigurationError) as captured:
            get_app_env({"APP_ENV": "staging-with-secret"})

        self.assertIn("development, test, production", str(captured.exception))
        self.assertNotIn("staging-with-secret", str(captured.exception))

    def test_test_redsea_database_is_rejected_by_guard(self):
        from backend.config import ConfigurationError, validate_test_database_url

        with self.assertRaises(ConfigurationError) as captured:
            validate_test_database_url("sqlite:///temporary/REDSEA_DEV.db")

        self.assertIn("TEST DATABASE SAFETY RULE VIOLATION", str(captured.exception))
        self.assertNotIn("REDSEA_DEV", str(captured.exception))

    def test_test_non_temporary_sqlite_is_rejected_by_guard(self):
        from backend.config import ConfigurationError, validate_test_database_url

        with self.assertRaises(ConfigurationError) as captured:
            validate_test_database_url("sqlite:///./redsea.db")

        self.assertIn("temporary directory", str(captured.exception))
        self.assertNotIn("redsea.db", str(captured.exception))

    def test_test_empty_database_url_is_rejected_by_guard(self):
        from backend.config import ConfigurationError, validate_test_database_url

        with self.assertRaises(ConfigurationError) as captured:
            validate_test_database_url(None)

        self.assertIn("TEST DATABASE SAFETY RULE VIOLATION", str(captured.exception))
        self.assertNotIn("sqlite:///", str(captured.exception))

    def test_test_temporary_sqlite_is_accepted_by_guard(self):
        from backend.config import validate_test_database_url

        path = Path(tempfile.gettempdir()) / "db0-isolated.sqlite"
        validate_test_database_url(f"sqlite:///{path.as_posix()}")
        validate_test_database_url("sqlite:///:memory:")

    def test_production_does_not_invoke_create_all(self):
        script = """
import json
from unittest.mock import patch
from sqlalchemy import MetaData

with patch.object(MetaData, "create_all") as create_all:
    import backend.main

print(json.dumps({"called": create_all.called}))
"""
        environment = os.environ.copy()
        environment["APP_ENV"] = "production"
        environment["DATABASE_URL"] = SQL_SERVER_URL
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=Path(__file__).resolve().parents[2],
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertEqual(json.loads(completed.stdout.strip()), {"called": False})


class _FailingEngine:
    dialect = SimpleNamespace(name="mssql")

    def connect(self):
        raise RuntimeError("SERVER_SENTINEL user-sentinel DATABASE_URL_SENTINEL")


class _ProbeConnection:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def execute(self, statement):
        rendered = str(statement)
        self.statements.append(rendered)
        if "version_num" in rendered:
            raise RuntimeError("no such table: alembic_version")
        return _ProbeResult()


class _ProbeResult:
    def fetchall(self):
        return [(1,)]


class _SuccessfulEngine:
    dialect = SimpleNamespace(name="sqlite")

    def __init__(self):
        self.connection = _ProbeConnection()

    def connect(self):
        return self.connection


class TestReadinessEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import backend.main as main

        cls.main = main
        cls.client = TestClient(main.app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        for name in list(sys.modules):
            if name == "backend" or name.startswith("backend."):
                sys.modules.pop(name, None)

    def test_liveness_does_not_access_database(self):
        with patch.object(self.main, "engine", _FailingEngine()):
            response = self.client.get("/health/live")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_readiness_failure_is_safe_and_returns_503(self):
        with patch.object(self.main, "engine", _FailingEngine()):
            response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 503)
        body = response.text
        self.assertEqual(
            response.json(),
            {"status": "degraded", "dialect": "mssql", "migration": "unavailable"},
        )
        for forbidden in ("SERVER_SENTINEL", "user-sentinel", "DATABASE_URL_SENTINEL", "Traceback"):
            self.assertNotIn(forbidden, body)

    def test_readiness_success_exposes_dialect_and_only_selects_one(self):
        engine = _SuccessfulEngine()
        with patch.object(self.main, "engine", engine):
            response = self.client.get("/health/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"status", "dialect", "migration"})
        self.assertEqual(response.json()["dialect"], "sqlite")
        self.assertEqual(response.json()["migration"], "unmanaged")
        self.assertEqual(
            engine.connection.statements,
            ["SELECT 1", "SELECT version_num FROM alembic_version"],
        )
        self.assertTrue(all(statement.lstrip().upper().startswith("SELECT") for statement in engine.connection.statements))
        for forbidden in (
            "DATABASE_URL",
            "SQLEXPRESS",
            "REDSEA_DEV",
            "Trusted_Connection",
            "pyodbc",
            "password",
        ):
            self.assertNotIn(forbidden.casefold(), response.text.casefold())
