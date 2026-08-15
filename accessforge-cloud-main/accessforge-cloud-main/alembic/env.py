from logging.config import fileConfig
import os

from alembic import context


config = context.config

# Programmatic callers can provide a one-shot, explicit migration target. Set
# it before backend.database is imported so its engine cannot use an application
# fallback URL. Normal Alembic CLI behaviour remains unchanged when absent.
explicit_database_url = config.attributes.get("database_url")
if explicit_database_url:
    os.environ["DATABASE_URL"] = explicit_database_url

# Importing database config constructs an engine but does not execute application
# startup. Importing models registers every current table on Base.
from backend.database import Base, DATABASE_URL, engine
import backend.models  # noqa: F401

if explicit_database_url and DATABASE_URL != explicit_database_url:
    raise RuntimeError("Alembic explicit database target did not bind to the configured engine.")

resolved_database_url = explicit_database_url or DATABASE_URL

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _escape_configparser_percent(value: str) -> str:
    """Escape percent signs for ConfigParser's BasicInterpolation."""

    return value.replace("%", "%%")


config.set_main_option("sqlalchemy.url", _escape_configparser_percent(resolved_database_url))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=resolved_database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
