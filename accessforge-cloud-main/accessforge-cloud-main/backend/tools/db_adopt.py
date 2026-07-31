"""Guarded adoption of a compatible existing SQLite database into Alembic."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ALEMBIC_INI = PROJECT_ROOT / "alembic.ini"
ALEMBIC_DIRECTORY = PROJECT_ROOT / "alembic"
BASELINE_REVISION = "a4fcbd8f8388"

EXIT_SUCCESS = 0
EXIT_REFUSED = 1
EXIT_FAILURE = 2
EXIT_ERROR = 3


@dataclass
class AdoptionResult:
    status: str
    database_path: str | None
    backup_path: str | None
    parity_decision: str | None
    starting_revision: str | None
    final_revision: str | None
    source_hash_before: str | None
    source_hash_after: str | None
    backup_hash: str | None
    row_count_summary: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    message: str = ""
    failure_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdoptionValidationError(ValueError):
    """An adoption target, confirmation, or backup is unsafe."""


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _target_path_and_url(target: str) -> tuple[Path, str]:
    if not target or not target.strip():
        raise AdoptionValidationError("An explicit absolute SQLite database path or URL is required.")
    target = target.strip()
    if "://" in target:
        try:
            url = sa.engine.make_url(target)
        except sa.exc.ArgumentError as exc:
            raise AdoptionValidationError(f"Invalid database URL: {exc}") from exc
        if url.get_backend_name() != "sqlite":
            raise AdoptionValidationError("Only SQLite targets are supported by adoption.")
        if not url.database or url.database == ":memory:" or url.query:
            raise AdoptionValidationError("A plain filesystem SQLite URL is required; memory and query URLs are refused.")
        candidate = Path(url.database)
    else:
        candidate = Path(target)
    if not candidate.is_absolute():
        raise AdoptionValidationError("The database target must be an absolute path.")
    path = candidate.expanduser().resolve(strict=False)
    if path.name.casefold() == "redsea.db":
        raise AdoptionValidationError("redsea.db is refused by adoption safety policy.")
    if not path.parent.is_dir():
        raise AdoptionValidationError(f"The target parent directory does not exist: {path.parent}")
    return path, f"sqlite:///{path.as_posix()}"


def _backup_path(value: str | None, source: Path) -> Path:
    if not value or not value.strip():
        raise AdoptionValidationError("An explicit backup path is required before stamping.")
    candidate = Path(value.strip())
    if not candidate.is_absolute():
        raise AdoptionValidationError("The backup path must be absolute.")
    path = candidate.expanduser().resolve(strict=False)
    if path == source:
        raise AdoptionValidationError("The backup path must not equal the source database path.")
    if not path.parent.is_dir():
        raise AdoptionValidationError(f"The backup parent directory does not exist: {path.parent}")
    if path.exists():
        raise AdoptionValidationError(f"Refusing to overwrite existing backup: {path}")
    return path


def _readonly_connection(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)


def _revision(path: Path) -> str | None:
    connection = _readonly_connection(path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        if "alembic_version" not in tables:
            return None
        rows = [row[0] for row in connection.execute("SELECT version_num FROM alembic_version")]
        if len(rows) != 1 or not rows[0]:
            raise AdoptionValidationError("alembic_version must contain exactly one non-empty revision.")
        return rows[0]
    finally:
        connection.close()


def _snapshot(path: Path) -> tuple[set[str], tuple[tuple[Any, ...], ...], dict[str, int], dict[str, tuple[tuple[Any, ...], ...]]]:
    """Capture schema and data facts needed to prove stamp-only preservation."""
    connection = _readonly_connection(path)
    try:
        all_tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
            if not row[0].startswith("sqlite_")
        }
        user_tables = sorted(all_tables - {"alembic_version"})
        schema = tuple(
            connection.execute(
                "SELECT type, name, tbl_name, sql FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY type, name"
            )
        )
        counts: dict[str, int] = {}
        samples: dict[str, tuple[tuple[Any, ...], ...]] = {}
        for table in user_tables:
            quoted = '"' + table.replace('"', '""') + '"'
            counts[table] = connection.execute(f"SELECT COUNT(*) FROM {quoted}").fetchone()[0]
            samples[table] = tuple(connection.execute(f"SELECT * FROM {quoted} LIMIT 3"))
        return all_tables, schema, counts, samples
    finally:
        connection.close()


def _run_parity(path: Path) -> tuple[str | None, list[str], str | None]:
    """Run parity in a fresh process so it cannot configure this stamp process."""
    environment = os.environ.copy()
    environment.pop("DATABASE_URL", None)
    completed = subprocess.run(
        [sys.executable, "-m", "backend.tools.schema_parity", "--database", str(path)],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None, [], f"Parity checker did not return structured output: {completed.stderr.strip()}"
    return payload.get("decision"), payload.get("warnings", []), None


def _stamp(target_url: str) -> None:
    cached_database = sys.modules.get("backend.database")
    if cached_database is not None and getattr(cached_database, "DATABASE_URL", None) != target_url:
        raise AdoptionValidationError("Refusing stamp because backend.database is configured for another target.")
    if not ALEMBIC_INI.is_file() or not ALEMBIC_DIRECTORY.is_dir():
        raise AdoptionValidationError("Alembic configuration is incomplete.")

    config = Config(str(ALEMBIC_INI))
    config.set_main_option("script_location", str(ALEMBIC_DIRECTORY))
    config.set_main_option("sqlalchemy.url", target_url)
    config.attributes["database_url"] = target_url
    original_url = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = target_url
    try:
        command.stamp(config, BASELINE_REVISION)
    finally:
        if original_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = original_url


def _recovery_message(source: Path, backup: Path, before_hash: str, backup_hash: str | None) -> str:
    return (
        f"Do not overwrite the source. Restore the verified backup manually if needed: {backup}. "
        f"Source before stamp SHA-256: {before_hash}; backup SHA-256: {backup_hash or 'unavailable'}."
    )


def adopt_sqlite(target: str, backup: str | None, confirm_stamp: str | None) -> AdoptionResult:
    """Stamp only a parity-compatible, existing non-Alembic SQLite database."""
    try:
        source, target_url = _target_path_and_url(target)
    except AdoptionValidationError as exc:
        return AdoptionResult("error", None, None, None, None, None, None, None, None, message=str(exc), failure_kind="validation")
    if not source.exists():
        return AdoptionResult("refused", str(source), None, None, None, None, None, None, None, message="Source database does not exist.")
    if not source.is_file():
        return AdoptionResult("refused", str(source), None, None, None, None, None, None, None, message="Source target is not a regular file.")

    try:
        parity_decision, parity_warnings, parity_error = _run_parity(source)
        starting_revision = _revision(source)
    except (sqlite3.DatabaseError, OSError, AdoptionValidationError) as exc:
        return AdoptionResult("error", str(source), None, None, None, None, None, None, None, message=f"Source inspection failed: {exc}", failure_kind="inspection")
    if parity_error:
        return AdoptionResult("error", str(source), None, None, None, None, None, None, None, message=parity_error, failure_kind="inspection")
    if parity_decision != "safe_to_stamp":
        return AdoptionResult("refused", str(source), None, parity_decision, starting_revision, starting_revision, None, None, None, warnings=parity_warnings, message="Parity decision must be safe_to_stamp before adoption.")
    if starting_revision is not None:
        if starting_revision == BASELINE_REVISION:
            return AdoptionResult("already_adopted", str(source), None, parity_decision, starting_revision, starting_revision, None, None, None, warnings=parity_warnings, message="Database is already stamped at the baseline revision.")
        return AdoptionResult("refused", str(source), None, parity_decision, starting_revision, starting_revision, None, None, None, warnings=parity_warnings, message="Existing Alembic revision conflicts with the baseline.")
    if confirm_stamp != BASELINE_REVISION:
        return AdoptionResult("refused", str(source), None, parity_decision, None, None, None, None, None, warnings=parity_warnings, message=f"Pass --confirm-stamp {BASELINE_REVISION} to authorize stamping.")

    try:
        backup_target = _backup_path(backup, source)
    except AdoptionValidationError as exc:
        return AdoptionResult("refused", str(source), None, parity_decision, None, None, None, None, None, warnings=parity_warnings, message=str(exc))

    source_hash_before = _hash(source)
    try:
        shutil.copyfile(source, backup_target)
        backup_hash = _hash(backup_target)
    except OSError as exc:
        return AdoptionResult("backup_failed", str(source), str(backup_target), parity_decision, None, None, source_hash_before, None, None, warnings=parity_warnings, message=f"Backup failed before stamp: {exc}", failure_kind="backup")
    if backup_hash != source_hash_before:
        return AdoptionResult("backup_failed", str(source), str(backup_target), parity_decision, None, None, source_hash_before, None, backup_hash, warnings=parity_warnings, message="Backup hash does not match source; stamping was not attempted.", failure_kind="backup")

    try:
        before_tables, before_schema, before_counts, before_samples = _snapshot(source)
        _stamp(target_url)
    except (AdoptionValidationError, sqlite3.DatabaseError, OSError, Exception) as exc:
        source_hash_after = _hash(source) if source.exists() else None
        return AdoptionResult("stamp_failed", str(source), str(backup_target), parity_decision, None, None, source_hash_before, source_hash_after, backup_hash, warnings=parity_warnings, message=f"Stamp failed. {_recovery_message(source, backup_target, source_hash_before, backup_hash)} Error: {exc}", failure_kind="stamp")

    source_hash_after = _hash(source)
    try:
        final_revision = _revision(source)
        after_tables, after_schema, after_counts, after_samples = _snapshot(source)
        final_parity, final_warnings, final_error = _run_parity(source)
        schema_unchanged = before_schema == after_schema
        data_unchanged = before_counts == after_counts and before_samples == after_samples
        only_version_added = after_tables == before_tables | {"alembic_version"}
        if (
            final_revision != BASELINE_REVISION
            or final_parity != "safe_to_stamp"
            or final_error is not None
            or not schema_unchanged
            or not data_unchanged
            or not only_version_added
        ):
            raise AdoptionValidationError("Post-stamp verification did not prove schema and data preservation.")
    except (sqlite3.DatabaseError, OSError, AdoptionValidationError) as exc:
        return AdoptionResult("verification_failed", str(source), str(backup_target), parity_decision, None, None, source_hash_before, source_hash_after, backup_hash, row_count_summary=before_counts, warnings=parity_warnings, message=f"Verification failed. {_recovery_message(source, backup_target, source_hash_before, backup_hash)} Error: {exc}", failure_kind="verification")

    return AdoptionResult("adopted", str(source), str(backup_target), final_parity, None, final_revision, source_hash_before, source_hash_after, backup_hash, row_count_summary=after_counts, warnings=final_warnings, message="Database was stamped after parity validation; user schema and data were preserved.")


def exit_code(result: AdoptionResult) -> int:
    if result.status in {"adopted", "already_adopted"}:
        return EXIT_SUCCESS
    if result.status == "refused":
        return EXIT_REFUSED
    if result.failure_kind in {"backup", "stamp", "verification"}:
        return EXIT_FAILURE
    return EXIT_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guarded SQLite Alembic adoption command")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database", help="Absolute filesystem path for the existing SQLite source")
    target.add_argument("--url", help="Absolute SQLite URL for the existing source")
    parser.add_argument("--backup", help="Absolute, non-existing backup path required before stamp")
    parser.add_argument("--confirm-stamp", help=f"Must exactly equal {BASELINE_REVISION}")
    args = parser.parse_args(argv)
    result = adopt_sqlite(args.database or args.url, args.backup, args.confirm_stamp)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
