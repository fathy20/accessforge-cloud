"""Regression coverage for Alembic URLs containing percent-encoded values."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_COMMAND = [sys.executable, "-m", "alembic", "upgrade", "head", "--sql"]
DATABASE_ENVIRONMENT_KEYS = (
    "DATABASE_URL",
    "SQL_SERVER_HOST",
    "SQL_SERVER_DRIVER",
    "SQL_SERVER_DB",
    "SQL_SERVER_TRUSTED_CONNECTION",
    "SQL_SERVER_USER",
    "SQL_SERVER_PASSWORD",
    "SQL_ECHO",
)

ENCODED_ODBC_DATABASE_URL = (
    "mssql+pyodbc:///?odbc_connect="
    "DRIVER%3D%7BODBC+Driver+17+for+SQL+Server%7D%3B"
    "SERVER%3Doffline-test-host%3BDATABASE%3Doffline_db%3B"
    "Trusted_Connection%3Dyes%3B"
)

PASSWORD_TOKEN = "NOT_A_REAL_PASSWORD_FOR_TESTS"
URL_WITH_PASSWORD = (
    "mssql+pyodbc:///?odbc_connect="
    "DRIVER%3D%7BODBC+Driver+17%7D%3B"
    "SERVER%3Doffline-test-host%3BDATABASE%3Doffline_db%3B"
    "UID%3Doffline_user%3BPWD%3D"
    f"{PASSWORD_TOKEN}%3BTrustServerCertificate%3Dyes%3B"
)

ROUND_TRIP_SCRIPT = r'''
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config


database_url = sys.argv[1]
alembic_config = Config(str(Path.cwd() / "alembic.ini"))
alembic_config.attributes["database_url"] = database_url
command.upgrade(alembic_config, "head", sql=True)

if alembic_config.get_main_option("sqlalchemy.url") != database_url:
    raise SystemExit(1)
'''


def _child_environment(
    *,
    app_env: str,
    database_url: str | None,
    **overrides: str,
) -> dict[str, str]:
    environment = os.environ.copy()
    for key in DATABASE_ENVIRONMENT_KEYS:
        environment.pop(key, None)

    environment["APP_ENV"] = app_env
    environment["PYTHON_DOTENV_DISABLED"] = "true"
    if database_url is not None:
        environment["DATABASE_URL"] = database_url
    environment.update(overrides)
    return environment


def _run_alembic(
    *,
    app_env: str,
    database_url: str | None,
    **overrides: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ALEMBIC_COMMAND,
        cwd=REPOSITORY_ROOT,
        env=_child_environment(
            app_env=app_env,
            database_url=database_url,
            **overrides,
        ),
        capture_output=True,
        text=True,
        check=False,
    )


class TestAlembicUrlHandling(unittest.TestCase):
    def test_percent_encoded_odbc_connect_url_runs_offline(self):
        completed = _run_alembic(
            app_env="production",
            database_url=ENCODED_ODBC_DATABASE_URL,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("CREATE TABLE", completed.stdout.upper())

    def test_documented_sql_server_environment_path_runs_offline(self):
        # Production intentionally requires DATABASE_URL before resolution can
        # reach the SQL_SERVER_* assembler in backend.config.
        completed = _run_alembic(
            app_env="development",
            database_url=None,
            SQL_SERVER_HOST="offline-documented-host",
            SQL_SERVER_TRUSTED_CONNECTION="yes",
        )

        self.assertEqual(completed.returncode, 0)

    def test_plain_sqlite_url_still_runs_offline(self):
        completed = _run_alembic(
            app_env="test",
            database_url="sqlite:///:memory:",
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("CREATE TABLE", completed.stdout.upper())

    def test_configparser_url_round_trip_returns_original_url(self):
        completed = subprocess.run(
            [sys.executable, "-c", ROUND_TRIP_SCRIPT, ENCODED_ODBC_DATABASE_URL],
            cwd=REPOSITORY_ROOT,
            env=_child_environment(app_env="production", database_url=None),
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(completed.returncode, 0)

    def test_offline_command_does_not_leak_url_or_password(self):
        completed = _run_alembic(
            app_env="production",
            database_url=URL_WITH_PASSWORD,
        )
        output = completed.stdout + completed.stderr

        self.assertEqual(completed.returncode, 0)
        self.assertFalse(PASSWORD_TOKEN in output)
        self.assertFalse(URL_WITH_PASSWORD in output)
