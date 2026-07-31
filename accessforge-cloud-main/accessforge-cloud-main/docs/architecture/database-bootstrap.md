# Explicit SQLite database bootstrap

`backend.tools.db_bootstrap` is the only supported command in this phase for creating a fresh developer or disposable SQLite schema. It uses `alembic upgrade head`; it does not import `backend.main`, run `create_all()`, execute runtime `ALTER TABLE`, stamp, downgrade, or seed application data.

## Usage

Pass one explicit, absolute target. The parent directory must already exist.

```powershell
python -m backend.tools.db_bootstrap --database "C:\work\scratch\redsea-dev.db"
python -m backend.tools.db_bootstrap --url "sqlite:///C:/work/scratch/redsea-dev.db"
```

The target URL is passed to Alembic through a one-shot configuration attribute and environment binding. `alembic.ini` is not modified, and the command never chooses `DATABASE_URL` or `redsea.db` as its target.

## Target-state policy

| State | Action |
| --- | --- |
| Missing path, zero-byte file, or valid SQLite database with no tables | Run `alembic upgrade head`. |
| Alembic revision at head and schema parity is compatible | Return `already_current`; write nothing. |
| Known Alembic revision behind head | Refuse unless `--upgrade-existing` is passed, then run `upgrade head`. |
| Non-Alembic schema or schema created by `Base.metadata.create_all()` | Refuse. Use the read-only parity checker and future adoption workflow; do not bootstrap it. |
| Unknown Alembic revision, invalid SQLite file, missing parent, relative path, non-SQLite URL, or a target named `redsea.db` | Refuse or return an operational error; write nothing. |

`--upgrade-existing` is intentionally narrow: it only permits a revision that exists in this repository's Alembic history and is behind the sole current head. It never permits unknown or non-Alembic schemas.

## Result and exit codes

The CLI prints structured JSON with `status`, target path, starting/target/final revisions, whether a migration ran, state, and message.

| Exit code | Meaning |
| --- | --- |
| `0` | Database was created, upgraded, or was already current. |
| `1` | Unsafe existing database was refused. |
| `2` | Alembic migration failed. |
| `3` | Invalid arguments, target validation, or operational inspection error. |

## Existing databases

Do not use this command directly on an existing non-Alembic database. First make a verified backup, then run [the read-only parity checker](schema-parity-checker.md) on an explicit copy. A future guarded adoption task may stamp only a database that has been proven compatible; this bootstrap command never stamps.