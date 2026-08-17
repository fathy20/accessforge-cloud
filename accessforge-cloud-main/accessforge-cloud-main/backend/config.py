"""Application environment and database configuration."""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Final, Literal, Mapping, cast
from urllib.parse import quote_plus, unquote

from dotenv import load_dotenv
from sqlalchemy.engine import make_url


logger = logging.getLogger(__name__)


def resolve_environment_files(backend_dir: Path) -> tuple[Path, ...]:
    """Return the .env files to load, most significant first."""

    candidates = (backend_dir.parent / ".env", backend_dir / ".env")
    return tuple(path for path in candidates if path.is_file())


def load_environment_files(backend_dir: Path) -> tuple[Path, ...]:
    """Load each resolved .env file without overriding values already set."""

    environment_files = resolve_environment_files(backend_dir)
    for path in environment_files:
        load_dotenv(path, override=False)

    if environment_files:
        logger.info("Loaded environment files: %s", ", ".join(str(path) for path in environment_files))
    else:
        logger.info("No environment files found.")
    return environment_files


# Bare load_dotenv() was cwd-dependent and stopped after one file, silently skipping backend/.env.
_BACKEND_DIR: Final = Path(__file__).resolve().parent
ENV_FILES_LOADED: Final[tuple[Path, ...]] = load_environment_files(_BACKEND_DIR)

AppEnv = Literal["development", "test", "production"]
ALLOWED_APP_ENVS: Final[tuple[AppEnv, ...]] = ("development", "test", "production")
DEFAULT_DATABASE_URL: Final = "sqlite:///./redsea.db"


class ConfigurationError(RuntimeError):
    """Raised when a safety-critical application setting is invalid."""


def should_auto_create_schema(app_env: str, dialect_name: str) -> bool:
    """Allow automatic schema creation only for SQLite development/test engines."""

    return app_env in ("development", "test") and dialect_name == "sqlite"


def _safe_configuration_error(variable: str, reason: str) -> ConfigurationError:
    """Build an error from fixed labels without including configured values."""

    return ConfigurationError(f"{variable}: {reason}")


def _test_safety_violation(reason: str) -> ConfigurationError:
    return ConfigurationError(f"TEST DATABASE SAFETY RULE VIOLATION: {reason}")


def get_app_env(environment: Mapping[str, str] | None = None) -> AppEnv:
    """Return the explicitly selected application environment."""

    source = os.environ if environment is None else environment
    if "APP_ENV" not in source:
        return "development"

    value = source.get("APP_ENV")
    if value not in ALLOWED_APP_ENVS:
        raise _safe_configuration_error(
            "APP_ENV",
            "must be one of: development, test, production",
        )
    return cast(AppEnv, value)


def _read_flag(environment: Mapping[str, str], name: str, default: bool = False) -> bool:
    value = environment.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def sql_echo_enabled(environment: Mapping[str, str] | None = None) -> bool:
    source = os.environ if environment is None else environment
    return _read_flag(source, "SQL_ECHO")


def _assemble_sql_server_url(environment: Mapping[str, str]) -> str | None:
    host = environment.get("SQL_SERVER_HOST", "").strip()
    if not host:
        return None

    driver = environment.get("SQL_SERVER_DRIVER", "ODBC Driver 17 for SQL Server").strip()
    database = environment.get("SQL_SERVER_DB", "redsea_db").strip() or "redsea_db"
    trusted_connection = _read_flag(environment, "SQL_SERVER_TRUSTED_CONNECTION")
    user = environment.get("SQL_SERVER_USER", "").strip()
    password = environment.get("SQL_SERVER_PASSWORD", "")

    connection_parts = [
        f"DRIVER={{{driver}}}",
        f"SERVER={host}",
        f"DATABASE={database}",
    ]
    if trusted_connection:
        connection_parts.extend(("Trusted_Connection=yes", "TrustServerCertificate=yes"))
    elif user and password:
        connection_parts.extend((f"UID={user}", f"PWD={password}", "TrustServerCertificate=yes"))
    else:
        return None

    params = quote_plus(";".join(connection_parts) + ";")
    return f"mssql+pyodbc:///?odbc_connect={params}"


def _parsed_database_url(database_url: str):
    if "://" not in database_url:
        raise _safe_configuration_error("DATABASE_URL", "must be a valid SQLAlchemy URL")
    try:
        parsed = make_url(database_url)
        if not parsed.drivername:
            raise ValueError
        parsed.get_backend_name()
    except Exception:
        raise _safe_configuration_error("DATABASE_URL", "must be a valid SQLAlchemy URL") from None
    return parsed


def database_dialect(database_url: str) -> str:
    """Return only the SQLAlchemy backend name, never a driver or connection string."""

    try:
        return make_url(database_url).get_backend_name()
    except Exception:
        return "unknown"


def _sqlite_file_is_temporary(parsed_url) -> bool:
    if parsed_url.database == ":memory:":
        return True
    if not parsed_url.database:
        return False

    path_text = unquote(parsed_url.database)
    if len(path_text) >= 3 and path_text[0] == "/" and path_text[2] == ":":
        path_text = path_text[1:]

    path = Path(path_text)
    if not path.is_absolute():
        return False

    try:
        temporary_root = Path(tempfile.gettempdir()).resolve()
        resolved_path = path.resolve()
        return resolved_path == temporary_root or temporary_root in resolved_path.parents
    except (OSError, RuntimeError, ValueError):
        return False


def validate_test_database_url(database_url: str | None) -> None:
    """Reject every test database target except memory or an absolute temp SQLite file."""

    if database_url is None or not database_url.strip():
        raise _test_safety_violation("DATABASE_URL must be configured as an isolated temporary SQLite database")

    candidate = database_url.strip()
    lowered = candidate.casefold()
    if "redsea_dev" in lowered:
        raise _test_safety_violation("DATABASE_URL must not reference the development database")
    if "sqlexpress" in lowered:
        raise _test_safety_violation("DATABASE_URL must not reference SQL Express")
    if "mssql" in lowered or "pyodbc" in lowered:
        raise _test_safety_violation("DATABASE_URL must not use an mssql or pyodbc dialect")

    parsed_url = _parsed_database_url(candidate)
    if parsed_url.get_backend_name() != "sqlite":
        raise _test_safety_violation("DATABASE_URL must use SQLite for tests")
    if not _sqlite_file_is_temporary(parsed_url):
        raise _test_safety_violation("SQLite test files must be absolute paths under the temporary directory")


def resolve_database_url(
    app_env: AppEnv | str | None = None,
    environment: Mapping[str, str] | None = None,
) -> str:
    """Resolve and validate the application database URL without connecting to it."""

    source = os.environ if environment is None else environment
    resolved_env = get_app_env(source) if app_env is None else get_app_env({"APP_ENV": app_env})
    configured_url = source.get("DATABASE_URL")
    has_explicit_url = configured_url is not None and bool(configured_url.strip())

    if resolved_env == "production" and not has_explicit_url:
        raise _safe_configuration_error("DATABASE_URL", "is required in production")

    if has_explicit_url:
        database_url = configured_url.strip()
    else:
        database_url = _assemble_sql_server_url(source)
        if database_url is None:
            if resolved_env == "test":
                raise _test_safety_violation(
                    "DATABASE_URL must be configured as a temporary SQLite URL before database import"
                )
            database_url = DEFAULT_DATABASE_URL

    parsed_url = _parsed_database_url(database_url)
    dialect = parsed_url.get_backend_name()

    if resolved_env == "production" and dialect == "sqlite":
        raise _safe_configuration_error("DATABASE_URL", "must not use SQLite in production")
    if resolved_env == "test":
        validate_test_database_url(database_url)

    return database_url


DEFAULT_CORS_ORIGINS: Final[tuple[str, ...]] = (
    "http://localhost:3000",
    "http://localhost:5173",
)


def resolve_cors_origins(
    app_env: AppEnv | str,
    environment: Mapping[str, str] | None = None,
) -> list[str]:
    """Parse CORS_ORIGINS into a trimmed, wildcard-free origin list.

    The middleware runs with allow_credentials=True, and credentialed CORS
    forbids a wildcard origin — browsers reject it, so a configured "*" was
    never functional, only misleading. Production refuses it outright;
    development drops it with a warning. Entries are trimmed and trailing
    slashes removed because origin matching is exact.
    """

    source = os.environ if environment is None else environment
    raw = source.get("CORS_ORIGINS")
    if raw is None or not raw.strip():
        return list(DEFAULT_CORS_ORIGINS)

    origins = [entry.strip().rstrip("/") for entry in raw.split(",")]
    origins = [origin for origin in origins if origin]
    if "*" in origins:
        if app_env == "production":
            raise _safe_configuration_error(
                "CORS_ORIGINS",
                "must not contain '*'; credentialed CORS forbids a wildcard origin",
            )
        logger.warning("Ignoring wildcard CORS origin; credentialed CORS cannot use '*'.")
        origins = [origin for origin in origins if origin != "*"]
    return origins or list(DEFAULT_CORS_ORIGINS)


APP_ENV: AppEnv = get_app_env()
DATABASE_URL: str = resolve_database_url(APP_ENV)
SELF_SIGNUP_ENABLED: bool = _read_flag(os.environ, "SELF_SIGNUP_ENABLED", default=True)
