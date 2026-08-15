from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIRECTORY = PROJECT_ROOT / "alembic"
BASELINE_REVISION = "f7a8b9c0d1e2"
EXPECTED_HEAD = "b8c9d0e1f2a3"


def _database_url(database_path: Path) -> str:
    return f"sqlite:///{database_path.as_posix()}"


def _alembic_config(database_path: Path) -> Config:
    database_url = _database_url(database_path)
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIRECTORY))
    config.set_main_option("sqlalchemy.url", database_url)
    config.attributes["database_url"] = database_url
    return config


def _clear_backend_modules() -> None:
    database_module = sys.modules.get("backend.database")
    if database_module is not None:
        database_module.engine.dispose()

    for name in list(sys.modules):
        if name == "backend" or (name.startswith("backend.") and not name.startswith("backend.tests")):
            sys.modules.pop(name, None)


def _upgrade(database_path: Path, revision: str) -> None:
    _clear_backend_modules()
    database_url = _database_url(database_path)
    original_database_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = database_url
    try:
        command.upgrade(_alembic_config(database_path), revision)
    finally:
        _clear_backend_modules()
        if original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_database_url


def test_null_user_status_is_backfilled_and_future_nulls_are_rejected(tmp_path: Path):
    database_path = tmp_path / "status-migration.sqlite"
    _upgrade(database_path, BASELINE_REVISION)

    engine = sa.create_engine(_database_url(database_path))
    try:
        with engine.begin() as connection:
            connection.execute(
                sa.text(
                    "INSERT INTO users (id, email, status) "
                    "VALUES (:id, :email, NULL)"
                ),
                {
                    "id": "null-status-user",
                    "email": "null-status-user@example.test",
                },
            )

        _upgrade(database_path, "head")

        with engine.connect() as connection:
            status = connection.scalar(
                sa.text("SELECT status FROM users WHERE id = :id"),
                {"id": "null-status-user"},
            )
            status_column = next(
                row for row in connection.execute(sa.text("PRAGMA table_info(users)")) if row[1] == "status"
            )

        assert status == "active"
        assert status_column[3] == 1
        assert status_column[4] is not None

        with pytest.raises(sa.exc.IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    sa.text(
                        "INSERT INTO users (id, email, status) "
                        "VALUES (:id, :email, NULL)"
                    ),
                    {
                        "id": "second-null-status-user",
                        "email": "second-null-status-user@example.test",
                    },
                )
    finally:
        engine.dispose()


def test_clean_sqlite_upgrade_reaches_expected_head(tmp_path: Path):
    database_path = tmp_path / "clean-upgrade.sqlite"

    _upgrade(database_path, "head")

    engine = sa.create_engine(_database_url(database_path))
    try:
        with engine.connect() as connection:
            revisions = connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalars().all()
        assert revisions == [EXPECTED_HEAD]
    finally:
        engine.dispose()
