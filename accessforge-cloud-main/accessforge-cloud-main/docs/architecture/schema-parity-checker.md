# Read-only SQLite schema parity checker

`backend.tools.schema_parity` compares an explicitly supplied, existing SQLite file with the current `Base.metadata`. It is an adoption diagnostic only: it never stamps, migrates, repairs, seeds, or starts the FastAPI application.

## Invocation

Run one of the following commands from the backend repository directory:

```powershell
python -m backend.tools.schema_parity --database "C:\absolute\path\to\copy.db"
python -m backend.tools.schema_parity --url "sqlite:///C:/absolute/path/to/copy.db"
```

The target must be an existing filesystem SQLite database. The checker rejects missing paths, `:memory:`, URL query parameters, and non-SQLite URLs. It never uses `DATABASE_URL` as an inspection target: metadata imports are pinned to an in-memory SQLite engine, so it cannot select `redsea.db` unless that exact path is explicitly passed by an operator.

The checker opens the target using SQLite URI `mode=ro`, records its SHA-256 and modification time before inspection, and verifies both values afterward. A detected change is a critical difference and can never yield `safe_to_stamp`.

## Result and exit codes

The CLI prints JSON with `status`, `decision`, `database_path`, `expected_revision`, `summary`, `differences`, `warnings`, and `inspection_limitations`.

| Exit code | Status | Meaning |
| --- | --- | --- |
| `0` | `compatible` | `safe_to_stamp`: no material parity differences. The checker still does not stamp. |
| `1` | `incompatible` | A material conflict exists, or an extra structure needs an explicit repair/adoption decision. |
| `2` | `unverifiable` | A critical inspection category could not be examined conclusively. Do not stamp. |
| `3` | `error` | Invalid argument, missing file, non-SQLite target, or operational inspection error. |

## Decision rules

- `safe_to_stamp`: all expected tables, columns, PKs, FKs, indexes, unique constraints, check constraints, compatible types, and nullability match. The `alembic_version` table is excluded from model-table comparison only; if present, its row must equal `a4fcbd8f8388`.
- `repair_required`: the expected schema is otherwise present but an unexpected extra table or column exists. The checker never repairs it.
- `incompatible`: a required table/column is absent or a PK, FK, type, nullable flag, index, unique constraint, or check constraint conflicts.
- `unverifiable`: SQLite reflection cannot inspect a critical category. This is blocking even if no other difference was found.

## SQLite limits

SQLite reflection may not preserve the original distinction between a `UniqueConstraint` and a unique index. JSON and Enum values are compared by safe storage-family compatibility rather than raw DDL strings; unknown types are never silently accepted. Column order is reported as non-semantic and is not compared.

Run this checker on a verified copy before any future `alembic stamp a4fcbd8f8388`. It is not a replacement for backup, data-integrity checks, or the guarded adoption workflow described in [Task 0.4](task-0.4-runtime-ddl-retirement-plan.md).
