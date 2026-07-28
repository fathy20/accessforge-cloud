# Guarded SQLite database adoption

`backend.tools.db_adopt` adopts an **existing compatible non-Alembic SQLite database copy** into the current Alembic baseline. It is not a schema migration tool: it never runs `upgrade`, `downgrade`, runtime DDL, seed logic, or automatic repair.

## When adoption is appropriate

Use adoption only after the read-only [schema parity checker](schema-parity-checker.md) returns exactly `safe_to_stamp` for an existing database. A matching existing schema must be stamped, not upgraded: `alembic upgrade head` would attempt to create tables that already exist.

Never use this command directly on production or `redsea.db` without a reviewed operational runbook. This task intentionally refuses any target named `redsea.db` and supports SQLite only.

## Required invocation

All paths must be absolute. The backup directory must already exist, and the backup file must not exist.

```powershell
python -m backend.tools.db_adopt `
  --database "C:\work\copies\redsea-compatible-copy.db" `
  --backup "C:\work\copies\redsea-compatible-copy.before-adoption.db" `
  --confirm-stamp a4fcbd8f8388
```

The exact confirmation value is required for a new stamp. Before stamping, the command:

1. runs the parity checker in an isolated read-only process;
2. refuses every result other than `safe_to_stamp`;
3. records the source hash;
4. creates a byte-for-byte backup and verifies its hash;
5. runs only `alembic.command.stamp(config, "a4fcbd8f8388")` with the explicit target URL; and
6. verifies revision, schema snapshot, table row counts, representative row values, and post-stamp parity.

## Existing adoption states

| State | Result |
| --- | --- |
| Compatible non-Alembic schema + exact confirmation + verified backup | `adopted` |
| Already stamped at `a4fcbd8f8388` and still parity-compatible | `already_adopted`; no confirmation or new backup is required. |
| `repair_required`, `incompatible`, or `unverifiable` parity | `refused`; no backup or stamp. |
| Unknown/conflicting Alembic revision | `refused`. |
| Missing, invalid, non-SQLite, relative, or `redsea.db` target | Refused or operational error; no write. |

## Exit codes and recovery

| Exit code | Meaning |
| --- | --- |
| `0` | `adopted` or `already_adopted` |
| `1` | Refused by a safety gate |
| `2` | Backup, stamp, or post-stamp verification failure |
| `3` | Invalid argument or operational inspection error |

If a failure occurs after a verified backup is created, the command reports the source/backup paths and hashes and instructs the operator to restore the backup manually. It never overwrites the source automatically.