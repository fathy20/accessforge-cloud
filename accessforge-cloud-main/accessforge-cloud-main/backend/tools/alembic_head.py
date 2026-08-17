"""Derive the single Alembic head from the migration scripts on disk.

The head revision used to be hardcoded in six places (tools and tests), so
every new migration required a synchronized edit of all of them and a miss
produced confusing "behind head" behavior. Everything now derives the value
from the scripts themselves; a repository with zero or multiple heads is an
error, never a silent guess.

This module reads only migration files. It never touches DATABASE_URL,
backend.database, or any database.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def _script_directory() -> ScriptDirectory:
    # Point at the versions directory absolutely: a relative script_location
    # in alembic.ini resolves against the process cwd, which tools and tests
    # cannot control.
    project_root = Path(__file__).resolve().parents[2]
    config = Config()
    config.set_main_option("script_location", str(project_root / "alembic"))
    return ScriptDirectory.from_config(config)


def expected_migration_head() -> str:
    """Return the one true head revision, or raise if the chain is broken."""

    heads = _script_directory().get_heads()
    if len(heads) != 1:
        raise RuntimeError(
            f"Expected exactly one Alembic head, found {len(heads)}: {heads}"
        )
    return heads[0]
