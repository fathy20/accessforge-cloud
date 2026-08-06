from __future__ import annotations

import re
import time
from enum import Enum
from typing import Any, Callable

from sqlalchemy import MetaData, create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.exc import (
    DisconnectionError,
    IntegrityError,
    OperationalError,
    ProgrammingError,
    TimeoutError as SQLAlchemyTimeoutError,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import (
    ConfigurationError,
    database_dialect,
    get_app_env,
    resolve_database_url,
    sql_echo_enabled,
)


class DatabaseFailureKind(Enum):
    """Coarse database failure classes used by the deferred retry policy."""

    TRANSIENT = "transient"
    TIMEOUT = "timeout"
    DEADLOCK = "deadlock"
    INTEGRITY = "integrity"
    PROGRAMMING = "programming"
    UNKNOWN = "unknown"


_DEADLOCK_ERROR_NUMBERS = frozenset({1205})
_TIMEOUT_ERROR_NUMBERS = frozenset({-2})
_TRANSIENT_ERROR_NUMBERS = frozenset(
    {64, 233, 4060, 40197, 40501, 40613, 49918, 49919, 49920, 10928, 10929}
)
_KNOWN_ERROR_NUMBERS = (
    _DEADLOCK_ERROR_NUMBERS | _TIMEOUT_ERROR_NUMBERS | _TRANSIENT_ERROR_NUMBERS
)
_ERROR_NUMBER_PATTERN = re.compile(r"(?<!\d)-?\d{1,5}(?!\d)")


def _sql_server_error_numbers(exc: BaseException) -> set[int]:
    """Extract only known SQL Server numbers from the wrapped DB-API error."""

    original = getattr(exc, "orig", None)
    values: list[Any] = []
    if original is not None:
        values.append(original)
        values.extend(getattr(original, "args", ()))
    else:
        values.extend(getattr(exc, "args", ()))
    for attribute in ("number", "error_number"):
        value = getattr(original, attribute, None)
        if value is not None:
            values.append(value)

    numbers: set[int] = set()
    for value in values:
        if isinstance(value, int) and not isinstance(value, bool):
            if value in _KNOWN_ERROR_NUMBERS:
                numbers.add(value)
            continue
        for match in _ERROR_NUMBER_PATTERN.finditer(str(value)):
            number = int(match.group())
            if number in _KNOWN_ERROR_NUMBERS:
                numbers.add(number)
    return numbers


def classify_database_error(exc: BaseException) -> DatabaseFailureKind:
    """Classify a SQLAlchemy/SQL Server failure without making retry decisions."""

    if isinstance(exc, IntegrityError):
        return DatabaseFailureKind.INTEGRITY
    if isinstance(exc, ProgrammingError):
        return DatabaseFailureKind.PROGRAMMING
    if isinstance(exc, SQLAlchemyTimeoutError):
        return DatabaseFailureKind.TIMEOUT
    if isinstance(exc, DisconnectionError):
        return DatabaseFailureKind.TRANSIENT
    if isinstance(exc, OperationalError):
        error_numbers = _sql_server_error_numbers(exc)
        if error_numbers & _DEADLOCK_ERROR_NUMBERS:
            return DatabaseFailureKind.DEADLOCK
        if error_numbers & _TIMEOUT_ERROR_NUMBERS:
            return DatabaseFailureKind.TIMEOUT
        if error_numbers & _TRANSIENT_ERROR_NUMBERS:
            return DatabaseFailureKind.TRANSIENT
        if getattr(exc, "connection_invalidated", False):
            return DatabaseFailureKind.TRANSIENT
    return DatabaseFailureKind.UNKNOWN


_RETRYABLE_FAILURES = frozenset(
    {
        DatabaseFailureKind.TRANSIENT,
        DatabaseFailureKind.TIMEOUT,
        DatabaseFailureKind.DEADLOCK,
    }
)


def retry_idempotent(
    operation: Callable[[], Any], *, attempts: int = 3, base_delay: float = 0.1
) -> Any:
    """Run a bounded idempotent operation with exponential backoff.

    Callers MUST reset transaction state with ``rollback()`` before each retry.
    Only TRANSIENT, TIMEOUT, and DEADLOCK failures are retryable. INTEGRITY,
    PROGRAMMING, and UNKNOWN failures are never retried. This helper must not
    be used for user creation, permission assignment, artifact creation, job
    submission, or any write lacking an idempotency key. It is intentionally not
    wired into application code in this slice.
    """

    if not isinstance(attempts, int) or isinstance(attempts, bool) or attempts < 1:
        raise ValueError("attempts must be a positive integer")
    if base_delay < 0:
        raise ValueError("base_delay must not be negative")

    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            if classify_database_error(exc) not in _RETRYABLE_FAILURES or attempt == attempts - 1:
                raise
            time.sleep(base_delay * (2**attempt))

    raise RuntimeError("retry operation exhausted without a result")


def engine_options_for(dialect_name: str, app_env: str) -> dict[str, Any]:
    """Return pure, dialect-specific ``create_engine`` kwargs."""

    if dialect_name == "sqlite":
        return {"connect_args": {"check_same_thread": False}}
    if dialect_name == "mssql":
        return {
            "pool_pre_ping": True,  # Validate pooled connections before use; idle TCP sessions can be silently dropped.
            "pool_size": 10,  # Keep ten steady-state concurrent connections available.
            "max_overflow": 20,  # Allow burst headroom while capping the pool at thirty connections.
            "pool_recycle": 3600,  # Recycle before common one-hour idle connection timeouts.
            "pool_timeout": 30,  # Bound pool-exhaustion waits instead of blocking request threads indefinitely.
            "connect_args": {"timeout": 10},  # Bound the pyodbc login wait so unreachable servers fail fast.
        }
    return {"pool_pre_ping": True}


def create_database_engine(database_url: str, app_env: str) -> Engine:
    """Create the application engine without opening a database connection."""

    try:
        dialect_name = database_dialect(database_url)
        options = engine_options_for(dialect_name, app_env)
        if dialect_name == "mssql":
            options["echo"] = sql_echo_enabled() and app_env != "production"
        return create_engine(database_url, **options)
    except Exception:
        raise ConfigurationError("DATABASE_URL could not initialize a database engine.") from None


APP_ENV = get_app_env()
DATABASE_URL = resolve_database_url(APP_ENV)
_DIALECT = database_dialect(DATABASE_URL)

# Build the engine without opening a connection. Configuration failures are kept
# value-free so a malformed or unusable target cannot leak connection details.
engine = create_database_engine(DATABASE_URL, APP_ENV)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_name)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(column_0_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = MetaData(naming_convention=NAMING_CONVENTION)
Base = declarative_base(metadata=metadata)


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
