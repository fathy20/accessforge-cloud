"""Read-only SQLite schema parity inspection for the current SQLAlchemy metadata.

This module deliberately accepts an explicit target only.  It never reads
``DATABASE_URL``, imports ``backend.main``, invokes Alembic, or performs DDL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKeyConstraint, UniqueConstraint, create_engine, inspect
from sqlalchemy.pool import StaticPool

# Importing models registers tables on Base.metadata. Force an in-memory URL
# only while those metadata modules are first imported, so a standalone checker
# process never selects an application DATABASE_URL or redsea.db. The checker
# never uses backend.database.engine; its inspection engine is created below
# from the explicit target and opened with SQLite mode=ro.
_original_database_url = os.environ.get("DATABASE_URL")
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
try:
    from backend.database import Base
    import backend.models  # noqa: F401
finally:
    if _original_database_url is None:
        os.environ.pop("DATABASE_URL", None)
    else:
        os.environ["DATABASE_URL"] = _original_database_url


BASELINE_REVISION = "e1a2b3c4d5f6"
IGNORED_TABLES = frozenset({"alembic_version"})

EXIT_COMPATIBLE = 0
EXIT_INCOMPATIBLE = 1
EXIT_UNVERIFIABLE = 2
EXIT_ERROR = 3


@dataclass(frozen=True)
class Difference:
    category: str
    object_name: str
    expected: Any
    actual: Any
    severity: str
    explanation: str


@dataclass
class ParityResult:
    status: str
    decision: str
    database_path: str | None
    expected_revision: str = BASELINE_REVISION
    summary: dict[str, Any] = field(default_factory=dict)
    differences: list[Difference] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    inspection_limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "decision": self.decision,
            "database_path": self.database_path,
            "expected_revision": self.expected_revision,
            "summary": self.summary,
            "differences": [asdict(difference) for difference in self.differences],
            "warnings": self.warnings,
            "inspection_limitations": self.inspection_limitations,
        }


class TargetValidationError(ValueError):
    """The supplied inspection target is not a safe, explicit SQLite file."""


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _target_path(target: str) -> Path:
    """Resolve an existing SQLite file from an explicit path or SQLite URL."""
    if not target or not target.strip():
        raise TargetValidationError("An explicit SQLite database path or URL is required.")

    target = target.strip()
    if "://" in target:
        try:
            url = sa.engine.make_url(target)
        except sa.exc.ArgumentError as exc:
            raise TargetValidationError(f"Invalid database URL: {exc}") from exc

        if url.get_backend_name() != "sqlite":
            raise TargetValidationError("Only explicit SQLite paths or SQLite URLs are supported.")
        if not url.database or url.database == ":memory:":
            raise TargetValidationError("A filesystem SQLite database is required; in-memory databases are refused.")
        if url.query:
            raise TargetValidationError("SQLite URL query parameters are refused so read-only mode is controlled by the checker.")
        candidate = Path(url.database)
    else:
        candidate = Path(target)

    path = candidate.expanduser().resolve(strict=False)
    if not path.exists():
        raise TargetValidationError(f"SQLite database file does not exist: {path}")
    if not path.is_file():
        raise TargetValidationError(f"SQLite target is not a file: {path}")
    return path


def _readonly_engine(path: Path):
    """Create an inspector engine whose every connection is SQLite URI mode=ro."""
    readonly_uri = f"{path.as_uri()}?mode=ro"

    def connect_readonly() -> sqlite3.Connection:
        return sqlite3.connect(readonly_uri, uri=True)

    return create_engine("sqlite://", creator=connect_readonly, poolclass=StaticPool)


def _type_family(column_type: sa.types.TypeEngine[Any]) -> str:
    if isinstance(column_type, sa.JSON):
        return "json"
    if isinstance(column_type, sa.Enum):
        return "enum"
    if isinstance(column_type, sa.Text):
        return "text"
    if isinstance(column_type, sa.String):
        return "string"
    if isinstance(column_type, sa.DateTime):
        return "datetime"
    if isinstance(column_type, sa.Boolean):
        return "boolean"
    if isinstance(column_type, sa.Integer):
        return "integer"
    return f"unknown:{column_type.__class__.__name__}"


def _types_compatible(expected: sa.types.TypeEngine[Any], actual: sa.types.TypeEngine[Any]) -> bool:
    expected_family = _type_family(expected)
    actual_family = _type_family(actual)
    if expected_family == actual_family:
        expected_length = getattr(expected, "length", None)
        actual_length = getattr(actual, "length", None)
        return expected_length is None or actual_length is None or expected_length == actual_length
    # SQLite stores SQLAlchemy Enum values in a string-compatible column.
    if expected_family == "enum" and actual_family == "string":
        return True
    # SQLite JSON support is commonly reflected as JSON, TEXT, or VARCHAR.
    if expected_family == "json" and actual_family in {"json", "text", "string"}:
        return True
    return False


def _column_description(column: Any) -> dict[str, Any]:
    column_type = column["type"] if isinstance(column, dict) else column.type
    return {
        "name": column["name"] if isinstance(column, dict) else column.name,
        "type": str(column_type),
        "family": _type_family(column_type),
        "length": getattr(column_type, "length", None),
        "nullable": column["nullable"] if isinstance(column, dict) else column.nullable,
    }


def _normalise_fk(
    local_columns: Iterable[str], referred_table: str, referred_columns: Iterable[str], name: str | None
) -> tuple[tuple[str, ...], str, tuple[str, ...], str | None]:
    return (tuple(local_columns), referred_table, tuple(referred_columns), name)


def _add_difference(
    differences: list[Difference],
    category: str,
    object_name: str,
    expected: Any,
    actual: Any,
    severity: str,
    explanation: str,
) -> None:
    differences.append(
        Difference(
            category=category,
            object_name=object_name,
            expected=expected,
            actual=actual,
            severity=severity,
            explanation=explanation,
        )
    )


def _compare_table(inspector: Any, table: sa.Table, differences: list[Difference], limitations: list[str]) -> None:
    table_name = table.name
    try:
        actual_columns = {column["name"]: column for column in inspector.get_columns(table_name)}
        actual_pk = tuple(inspector.get_pk_constraint(table_name).get("constrained_columns") or ())
        actual_fks = {
            _normalise_fk(
                fk.get("constrained_columns") or (),
                fk.get("referred_table") or "",
                fk.get("referred_columns") or (),
                fk.get("name"),
            )
            for fk in inspector.get_foreign_keys(table_name)
        }
        actual_indexes = {
            (index.get("name"), tuple(index.get("column_names") or ()), bool(index.get("unique")))
            for index in inspector.get_indexes(table_name)
        }
        actual_unique = {
            (constraint.get("name"), tuple(constraint.get("column_names") or ()))
            for constraint in inspector.get_unique_constraints(table_name)
        }
        actual_checks = {
            (constraint.get("name"), (constraint.get("sqltext") or "").strip())
            for constraint in inspector.get_check_constraints(table_name)
        }
    except (NotImplementedError, sa.exc.SQLAlchemyError) as exc:
        limitations.append(f"Could not fully inspect {table_name}: {exc}")
        _add_difference(
            differences,
            "inspection",
            table_name,
            "full SQLite constraint inspection",
            "unavailable",
            "critical",
            "A critical schema category could not be inspected, so stamping is unsafe.",
        )
        return

    expected_columns = {column.name: column for column in table.columns}
    for name, expected_column in expected_columns.items():
        actual_column = actual_columns.get(name)
        if actual_column is None:
            _add_difference(
                differences, "column", f"{table_name}.{name}", _column_description(expected_column), None,
                "critical", "Expected column is missing."
            )
            continue
        if not _types_compatible(expected_column.type, actual_column["type"]):
            _add_difference(
                differences, "type", f"{table_name}.{name}", _column_description(expected_column),
                _column_description(actual_column), "critical", "Type family or declared length is incompatible."
            )
        if bool(expected_column.nullable) != bool(actual_column["nullable"]):
            _add_difference(
                differences, "nullable", f"{table_name}.{name}", expected_column.nullable,
                actual_column["nullable"], "critical", "Column nullability differs."
            )

    for name, actual_column in actual_columns.items():
        if name not in expected_columns:
            _add_difference(
                differences, "extra_column", f"{table_name}.{name}", None, _column_description(actual_column),
                "warning", "Unexpected column requires an explicit adoption decision; it is not ignored."
            )

    expected_pk = tuple(column.name for column in table.primary_key.columns)
    if expected_pk != actual_pk:
        _add_difference(
            differences, "primary_key", table_name, expected_pk, actual_pk,
            "critical", "Primary-key membership or ordering differs."
        )

    expected_fks = {
        _normalise_fk(
            constraint.column_keys,
            constraint.referred_table.name,
            [element.column.name for element in constraint.elements],
            constraint.name,
        )
        for constraint in table.foreign_key_constraints
    }
    if expected_fks != actual_fks:
        _add_difference(
            differences, "foreign_key", table_name, sorted(expected_fks), sorted(actual_fks),
            "critical", "Foreign-key local columns, targets, names, or ordering differ."
        )

    expected_indexes = {(index.name, tuple(column.name for column in index.columns), bool(index.unique)) for index in table.indexes}
    if expected_indexes != actual_indexes:
        _add_difference(
            differences, "index", table_name, sorted(expected_indexes), sorted(actual_indexes),
            "critical", "Index names, ordered columns, or unique flags differ."
        )

    expected_unique = {
        (constraint.name, tuple(column.name for column in constraint.columns))
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    if expected_unique != actual_unique:
        _add_difference(
            differences, "unique_constraint", table_name, sorted(expected_unique), sorted(actual_unique),
            "critical", "UniqueConstraint definitions differ from SQLite reflection."
        )

    expected_checks = {
        (constraint.name, str(constraint.sqltext).strip())
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    if expected_checks != actual_checks:
        _add_difference(
            differences, "check_constraint", table_name, sorted(expected_checks), sorted(actual_checks),
            "critical", "Check constraints differ from SQLite reflection."
        )


def _decision(differences: Sequence[Difference], limitations: Sequence[str]) -> tuple[str, str]:
    # Documented SQLite reflection limits are warnings. Only a failed inspection is blocking.
    if any(d.category == "inspection" for d in differences):
        return "unverifiable", "unverifiable"
    if any(d.severity == "critical" for d in differences):
        return "incompatible", "incompatible"
    if differences:
        return "incompatible", "repair_required"
    return "compatible", "safe_to_stamp"


def check_sqlite_schema(target: str) -> ParityResult:
    """Compare an explicit, existing SQLite file with ``Base.metadata`` read-only."""
    try:
        path = _target_path(target)
    except TargetValidationError as exc:
        return ParityResult(
            status="error",
            decision="unverifiable",
            database_path=None,
            summary={"error": str(exc)},
            warnings=["No database was opened because target validation failed."],
        )

    before_hash = _file_hash(path)
    before_mtime = path.stat().st_mtime_ns
    differences: list[Difference] = []
    warnings = ["SQLite was opened through a file: URI with mode=ro."]
    limitations = [
        "SQLite reflection cannot always preserve the original distinction between a UniqueConstraint and a unique index.",
        "Column order is intentionally informational and is not compared.",
        "SQLite enum and JSON storage are compared by compatible storage family, not raw DDL text.",
    ]

    engine = _readonly_engine(path)
    try:
        inspector = inspect(engine)
        actual_tables = set(inspector.get_table_names())
        expected_tables = set(Base.metadata.tables)

        ignored_present = sorted(actual_tables & IGNORED_TABLES)
        actual_revisions: list[str] = []
        if ignored_present:
            warnings.append("Excluded explicit infrastructure table(s) from model-table comparison: " + ", ".join(ignored_present))
            try:
                with engine.connect() as connection:
                    actual_revisions = list(connection.execute(sa.text("SELECT version_num FROM alembic_version")).scalars())
            except (sqlite3.Error, sa.exc.SQLAlchemyError) as exc:
                limitations.append(f"Could not read alembic_version safely: {exc}")
                _add_difference(
                    differences, "inspection", "alembic_version", "readable revision row", "unavailable",
                    "critical", "The infrastructure revision cannot be inspected, so stamping is unsafe."
                )
            else:
                if actual_revisions != [BASELINE_REVISION]:
                    _add_difference(
                        differences, "alembic_revision", "alembic_version", BASELINE_REVISION, actual_revisions,
                        "critical", "Existing Alembic revision differs from the current baseline."
                    )
        comparable_actual = actual_tables - IGNORED_TABLES

        for table_name in sorted(expected_tables - comparable_actual):
            _add_difference(
                differences, "table", table_name, "present", "missing", "critical", "Expected table is missing."
            )
        for table_name in sorted(comparable_actual - expected_tables):
            _add_difference(
                differences, "extra_table", table_name, "absent", "present", "warning",
                "Unexpected table is not ignored and requires an explicit repair/adoption decision."
            )
        for table_name in sorted(expected_tables & comparable_actual):
            _compare_table(inspector, Base.metadata.tables[table_name], differences, limitations)
    except (sqlite3.Error, sa.exc.SQLAlchemyError, OSError) as exc:
        return ParityResult(
            status="error",
            decision="unverifiable",
            database_path=str(path),
            summary={"error": str(exc)},
            warnings=warnings,
            inspection_limitations=limitations,
        )
    finally:
        engine.dispose()

    after_hash = _file_hash(path)
    after_mtime = path.stat().st_mtime_ns
    if before_hash != after_hash or before_mtime != after_mtime:
        _add_difference(
            differences, "read_only_enforcement", path.name,
            {"sha256": before_hash, "mtime_ns": before_mtime},
            {"sha256": after_hash, "mtime_ns": after_mtime},
            "critical", "The inspected database changed during a read-only inspection."
        )

    status, decision = _decision(differences, limitations)
    return ParityResult(
        status=status,
        decision=decision,
        database_path=str(path),
        summary={
            "expected_table_count": len(expected_tables),
            "actual_table_count": len(comparable_actual),
            "difference_count": len(differences),
            "actual_revisions": actual_revisions,
            "read_only_hash_unchanged": before_hash == after_hash,
            "read_only_mtime_unchanged": before_mtime == after_mtime,
        },
        differences=differences,
        warnings=warnings,
        inspection_limitations=limitations,
    )


def exit_code(result: ParityResult) -> int:
    if result.status == "compatible":
        return EXIT_COMPATIBLE
    if result.status == "incompatible":
        return EXIT_INCOMPATIBLE
    if result.status == "unverifiable":
        return EXIT_UNVERIFIABLE
    return EXIT_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only SQLite schema parity checker")
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--database", help="Explicit filesystem path to an existing SQLite database")
    target.add_argument("--url", help="Explicit SQLite URL for an existing filesystem database")
    args = parser.parse_args(argv)
    result = check_sqlite_schema(args.database or args.url)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True, default=str))
    return exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
