"""Collection-time database safety guard for pytest."""

from __future__ import annotations

import os
import sys


# Pytest must never collect tests under production database rules.
os.environ["APP_ENV"] = "test"

# Re-imported auth modules need a deliberately fake signing key in tests only.
os.environ.setdefault("JWT_SECRET_KEY", "TEST_ONLY_NOT_A_SECRET_JWT_KEY_32_CHARS")

# Existing tests choose their own temporary file before importing backend.database.
# A process-scoped in-memory target keeps import-only tests isolated when they do
# not need a file, while explicit unsafe targets are still rejected below.
if "DATABASE_URL" not in os.environ:
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from backend.config import ConfigurationError, validate_test_database_url


def enforce_test_database_safety(database_url: str | None = None) -> None:
    """Fail collection unless the effective test URL is an isolated SQLite target."""

    if "backend.database" in sys.modules:
        raise RuntimeError(
            "TEST DATABASE SAFETY RULE VIOLATION: backend.database was imported before collection guard"
        )

    try:
        validate_test_database_url(os.environ.get("DATABASE_URL") if database_url is None else database_url)
    except ConfigurationError as exc:
        raise RuntimeError(str(exc)) from None


enforce_test_database_safety()
