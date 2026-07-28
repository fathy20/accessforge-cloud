"""Explicit, SQLite-only Alembic bootstrap command.

The command creates or upgrades only the database target supplied by the
operator.  It does not use the application's DATABASE_URL as a target and is
not imported by the API startup path.
"""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIRECTORY = PROJECT_ROOT / "alembic"

EXIT_SUCCESS = 0
EXIT_REFUSED = 1
EXIT_MIGRATION_FAILURE = 2
EXIT_ERROR = 3


@dataclass
class BootstrapResult:
    status: str
    database_path: str | None
    starting_revision: str | None
    target_revision: str | None
    final_revision: str | None
    migrations_applied: bool
    database_state: str | None
    message: str
    warnings: list[str] = field(default_factory=list)
    failure_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BootstrapValidationError(ValueError):
    """The explicit target cannot be used safely for bootstrap."""


def _path_and_url(target: str) -> tuple[Path, str]:
    if not target or not target.strip():
        raise BootstrapValidationError("An explicit absolute SQLite database path or URL is required.")

    target = target.strip()
    if "://" in target:
        try:
            url = sa.engine.make_url(target)
        except sa.exc.ArgumentError as exc:
            raise BootstrapValidationError(f"Invalid database URL: {exc}") from exc
        if url.get_backend_name() != "sqlite":
            raise BootstrapValidationError("Only SQLite targets are supported by this command.")
        if not url.database or url.database == ":memory:" or url.query:
            raise BootstrapValidationError("A plain filesystem SQLite URL is required; memory and query URLs are refused.")
        candidate = Path(url.database)
    else:
        candidate = Path(target)

    if not candidate.is_absolute():
        raise BootstrapValidationError("The database target must be an absolute path.")
    path = candidate.expanduser().resolve(strict=False)
    if path.name.casefold() == "redsea.db":
        raise BootstrapValidationError("redsea.db is refused by bootstrap safety policy.")
    if not path.parent.is_dir():
        raise BootstrapValidationError(f"The target parent directory does not exist: {path.parent}")
    return path, f"sqlite:///{path.as_posix()}"


def _alembic_config(target_url: str) -> tuple[Config, ScriptDirectory, str]:
    if not ALEMBIC_INI.is_file() or not ALEMBIC_DIRECTORY.is_dir():
        raise BootstrapValidationError("Alembic configuration is incomplete.")
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIRECTORY))
    config.set_main_option("sqlalchemy.url", target_url)
    config.attributes["database_url"] = target_url
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    if len(heads) != 1:
        raise BootstrapValidationError("Bootstrap requires exactly one Alembic head revision.")
    return config, scripts, heads[0]


def _readonly_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)


def _inspect_existing(path: Path, scripts: ScriptDirectory, head: str) -> tuple[str, str | None, str | None]:
    """Return state, current revision, and a refusal/error message if applicable."""
    if not path.exists():
        return "missing", None, None
    if not path.is_file():
        return "invalid", None, "The target exists but is not a regular file."
    if path.stat().st_size == 0:
        return "empty_file", None, None

    try:
        connection = _readonly_connection(path)
        try:
            connection.execute("PRAGMA schema_version").fetchone()
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
                if not row[0].startswith("sqlite_")
            }
            if "alembic_version" in tables:
                revisions = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
                if len(revisions) != 1 or not revisions[0]:
                    return "incompatible", None, "alembic_version must contain exactly one non-empty revision."
                revision = revisions[0]
                if revision == head:
                    return "at_head", revision, None
                try:
                    known_revision = scripts.get_revision(revision)
                except Exception:
                    known_revision = None
                if known_revision is not None:
                    return "behind_head", revision, None
                return "incompatible", revision, "Database has an Alembic revision unknown to this codebase."
            if not tables:
                return "no_user_tables", None, None
            return "non_alembic_schema", None, "Existing schema is not Alembic-managed; use parity/adoption workflow."
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        return "invalid", None, f"Target is not a readable SQLite database: {exc}"
    except OSError as exc:
        return "invalid", None, f"Target cannot be inspected safely: {exc}"


def _current_revision(path: Path) -> str | None:
    connection = _readonly_connection(path)
    try:
        rows = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
    finally:
        connection.close()
    return rows[0] if len(rows) == 1 else None


def _run_upgrade(config: Config, target_url: str) -> None:
    cached_database = sys.modules.get("backend.database")
    if cached_database is not None and getattr(cached_database, "DATABASE_URL", None) != target_url:
        raise BootstrapValidationError(
            "Refusing bootstrap because backend.database is already configured for another target."
        )

    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = target_url
    try:
        command.upgrade(config, "head")
    finally:
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url


def _parity_message(path: Path) -> tuple[bool, str]:
    # Delayed import keeps metadata/application configuration out of preflight.
    from backend.tools.schema_parity import check_sqlite_schema

    parity = check_sqlite_schema(str(path))
    if parity.status == "compatible":
        return True, "Schema matches current SQLAlchemy metadata."
    return False, f"Post-bootstrap schema parity is {parity.status}/{parity.decision}."


def bootstrap_sqlite(target: str, *, upgrade_existing: bool = False) -> BootstrapResult:
    """Safely bootstrap an explicit SQLite target with ``alembic upgrade head``."""
    try:
        path, target_url = _path_and_url(target)
        config, scripts, head = _alembic_config(target_url)
    except BootstrapValidationError as exc:
        return BootstrapResult("error", None, None, None, None, False, None, str(exc), failure_kind="validation")

    state, starting_revision, state_message = _inspect_existing(path, scripts, head)
    if state == "invalid":
        return BootstrapResult("error", str(path), starting_revision, head, None, False, state, state_message or "Invalid target.", failure_kind="inspection")
    if state in {"non_alembic_schema", "incompatible"}:
        return BootstrapResult("refused", str(path), starting_revision, head, starting_revision, False, state, state_message or "Unsafe existing database.")
    if state == "at_head":
        compatible, message = _parity_message(path)
        if not compatible:
            return BootstrapResult("refused", str(path), starting_revision, head, starting_revision, False, state, message)
        return BootstrapResult("already_current", str(path), starting_revision, head, starting_revision, False, state, "Database is already at head. " + message)
    if state == "behind_head" and not upgrade_existing:
        return BootstrapResult("refused", str(path), starting_revision, head, starting_revision, False, state, "Database is behind head; rerun with --upgrade-existing after approval.")

    try:
        _run_upgrade(config, target_url)
        final_revision = _current_revision(path)
    except BootstrapValidationError as exc:
        return BootstrapResult("error", str(path), starting_revision, head, None, False, state, str(exc), failure_kind="validation")
    except Exception as exc:  # Alembic preserves the detailed failure in stderr/logging.
        return BootstrapResult("error", str(path), starting_revision, head, None, False, state, f"Alembic upgrade failed: {exc}", failure_kind="migration")

    if final_revision != head:
        return BootstrapResult("error", str(path), starting_revision, head, final_revision, True, state, "Alembic did not reach the expected head revision.", failure_kind="migration")
    compatible, message = _parity_message(path)
    if not compatible:
        return BootstrapResult("error", str(path), starting_revision, head, final_revision, True, state, message, failure_kind="migration")
    status = "upgraded" if state == "behind_head" else "created"
    return BootstrapResult(status, str(path), starting_revision, head, final_revision, True, state, "Alembic upgrade head completed. " + message)


def exit_code(result: BootstrapResult) -> int:
    if result.status in {"created", "upgraded", "already_current"}:
        return EXIT_SUCCESS
    if result.status == "refused":
        return EXIT_REFUSED
    if result.failure_kind == "migration":
        return EXIT_MIGRATION_FAILURE
    return EXIT_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicit SQLite Alembic bootstrap command")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database", help="Absolute filesystem path for the SQLite target")
    target.add_argument("--url", help="Absolute SQLite URL for the target")
    parser.add_argument("--upgrade-existing", action="store_true", help="Allow upgrade of a known Alembic revision behind head")
    args = parser.parse_args(argv)
    result = bootstrap_sqlite(args.database or args.url, upgrade_existing=args.upgrade_existing)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
