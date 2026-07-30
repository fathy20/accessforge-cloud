# Task 0.4 — Runtime DDL Retirement and Existing-Database Adoption Plan

## Scope and evidence

This is an inventory and cutover plan only. It does not change application behaviour, stamp a database, create a migration, access SQL Server, or access `REDSEA_DEV`.

Baseline facts at the time of this report:

- Branch: `codex/backend-dependency-manifest`
- Starting commit: `6ba6cd7`
- Alembic baseline revision: `a4fcbd8f8388`
- The baseline was validated on disposable SQLite databases only.
- `redsea.db` is un-stamped and must not receive `alembic upgrade head`; it already contains application tables.

Repository searches covered Python sources, Alembic configuration, tests, startup hooks, raw SQL, and common schema-mutation patterns. The current model tables are:

`users`, `user_roles`, `modules`, `uploads`, `jobs`, `projects`, `audit_log`, `notifications`, `user_invitations`, and `module_access`.

## 1. Runtime schema-mutation inventory

| Location | Scope / execution point | Purpose and affected schema | Classification | Removal risk | Replacement strategy |
| --- | --- | --- | --- | --- | --- |
| `backend/main.py:26` | Module import, before `FastAPI` is constructed | `Base.metadata.create_all(bind=engine)` creates every table registered in `Base.metadata` when absent. | Runtime schema DDL | High: it currently makes a fresh local API start succeed without a migration. Removing it first would break fresh databases and tests that import `backend.main`. | Run Alembic explicitly before API startup; add a schema-version diagnostic first, then remove only after fresh-install and adopted-database workflows pass. |
| `backend/main.py:29-41` (retired in Task 0.4.4) | Previously module import, immediately after `create_all()` | The generic loop that inspected every metadata table and added every missing modeled column with raw `ALTER TABLE` has been removed. | Retired runtime compatibility DDL | No startup schema repair is supported; outdated databases may fail naturally when application code uses a missing column. | Use parity verification plus `backend.tools.db_adopt` for compatible existing SQLite, or an explicit Alembic migration workflow for future revisions. |
| `backend/main.py:358-390` | FastAPI startup event | Creates a default admin and adds missing module rows. It changes data only; it does not create or alter tables. | Seed data | Medium: removing or moving it could change local-login and module-availability behaviour. | Keep separate from schema cutover. Later move it to an explicit idempotent seed/bootstrap command or retain it as clearly-labelled development-only seed behaviour. |
| `backend/tests/test_check_control.py:55` | Isolated test setup | Calls `Base.metadata.create_all()` on the test-owned SQLite engine after setting a temporary `DATABASE_URL` and changing to a temporary working directory. | Test-only schema setup | Low for production; medium for migration confidence because it bypasses Alembic. | Convert this fixture to `alembic upgrade head` against its temporary SQLite database in Task 0.4.7, after migrations own the schema. |
| `backend/tests/test_api_check_control.py:20-33` | Isolated test setup then `import backend.main` | Sets a temporary SQLite URL before importing the API. Importing `backend.main` still triggers the temporary `create_all()` path, but no longer performs runtime column repair. | Indirect test-only runtime DDL | Medium: the test is isolated, but it does not prove API startup without implicit schema mutation. | Keep isolation, then update the fixture to migrate its temp database before importing the API once Tasks 0.4.4 and 0.4.5 are complete. |
| `backend/database.py:12-67` | Backend module import | Resolves `DATABASE_URL` and constructs an engine. It does not issue schema DDL by itself. A SQLite file is created only when a later operation connects and writes. | Implicit database configuration | Medium: a missing explicit `DATABASE_URL` falls back to relative `./redsea.db`; an operator can target the wrong file. | Add path/URL diagnostics and require an explicit migration target in the migration/bootstrap workflow. Do not change fallback behaviour in Task 0.4 planning. |
| `alembic/env.py:20-42` | Only when an Alembic command is invoked | Opens the configured migration connection in online mode and applies or inspects migrations. | Explicit migration path | Intended behaviour | Preserve. Ensure deployment automation, not API/worker startup, invokes it. |

No other runtime SQL DDL, `drop_all`, table/index creation, PRAGMA schema mutation, or startup schema hook was found in the backend or worker sources. `local_storage` directory creation in `backend/main.py:80-82` is filesystem initialization, not database DDL.

## 2. Existing SQLite database adoption plan

The existing `redsea.db` is not a fresh database. Never run `alembic upgrade head` on it before adoption: the baseline creates existing tables and will conflict. The adoption path is **inspect → compare → decide → stamp**, not upgrade.

### Preconditions and backup

1. Stop API and worker processes that can write to the target database.
2. Resolve and print the exact absolute SQLite path from the operator-supplied `DATABASE_URL`; reject a relative path unless the operator explicitly confirms it.
3. Take a timestamped, immutable copy and record SHA-256 for both source and backup. Validate the backup with `PRAGMA integrity_check` in a read-only inspection process.
4. Record application commit, Alembic head (`a4fcbd8f8388` for the current baseline), Python/SQLAlchemy/Alembic versions, and the target file hash.
5. Confirm the target is not `REDSEA_DEV`, is not a SQL Server URL, and has not already been stamped with a different or unknown Alembic revision.

### Parity inspection

Task 0.4.1 should provide a read-only checker that compares the target database with `Base.metadata` and emits machine-readable JSON plus an operator-readable report. It must inspect:

1. expected and unexpected tables;
2. expected and unexpected columns per table;
3. PK, FK, index, and unique-constraint names and definitions;
4. reflected types, lengths, nullability, and server defaults;
5. model-required primary-key columns and expected foreign-key target columns;
6. `alembic_version`, if present;
7. `PRAGMA foreign_key_check` and `PRAGMA integrity_check` for SQLite; and
8. `alembic check` only against an explicitly confirmed copy/target after schema inspection has shown it is safe to connect.

The report must distinguish SQLAlchemy Python-side defaults from database server defaults. The current models use Python/ORM defaults; their absence from reflected SQLite server defaults is expected and is not a parity failure.

### Data-integrity checks before a stamp

The parity checker or its adoption wrapper must check at least:

- null or duplicate primary-key values in every table;
- duplicate values for the model's unique keys: `users.email`, `modules.key`, and `user_invitations.token`;
- orphan references for all modeled FKs, including `jobs.module_key → modules.key` and user-owned records;
- values outside the known enum sets for `jobs.status`, `uploads.kind`, and `user_roles.role` where stored values are non-null;
- values that would fail a future non-null or unique hardening migration; and
- `PRAGMA foreign_key_check` output, even though historic SQLite connections may not have enforced FKs.

### Adoption decision rules

| Result | Decision |
| --- | --- |
| Tables, columns, constraints/indexes, types/nullability, integrity checks, and `alembic check` match the current baseline; no unexpected `alembic_version` | Safe to stamp after a verified backup. |
| Differences are understood historical schema drift, data is preservable, and the desired end state is unambiguous | Do not stamp. Create and validate a narrow repair migration on a disposable copy first; repeat parity and integrity checks. |
| Missing core tables, incompatible types, broken FK/data integrity, conflicting unique data, or unexplained extra schema | Incompatible database. Stop and restore/use a backup or define a data-repair project; do not stamp. |
| `alembic_version` contains a revision absent from this branch or ahead of the current head | Database newer than code. Stop deployment/adoption; obtain the matching migration history. |

### Stamp and verification procedure

Only after the safe-to-stamp rule is met and an operator explicitly approves the exact target:

```powershell
$env:DATABASE_URL = "sqlite:///C:/absolute/path/to/confirmed-copy.db"
python -m alembic stamp a4fcbd8f8388
python -m alembic current --check-heads
python -m alembic check
```

`stamp` records a revision without running migrations; that is precisely why it is suitable only after parity verification. See the official Alembic [`stamp` command documentation](https://alembic.sqlalchemy.org/en/latest/api/commands.html#alembic.command.stamp) and its [existing-schema guidance](https://alembic.sqlalchemy.org/en/latest/cookbook.html#building-an-up-to-date-database-from-scratch).

Post-stamp verification must re-run the read-only parity report, confirm the expected revision in `alembic_version`, compare target and backup hashes only for expected version-table change, and start one API process with runtime DDL still enabled until the subsequent cutover tasks prove removal safe.

### Rollback and recovery

- If stamping fails or produces an unexpected schema result, stop the API/worker and restore the verified backup file; do not run a downgrade as a substitute for restoring unversioned historical data.
- If post-stamp parity fails, preserve the failed copy for analysis, restore the backup, and create a repair migration only after reproducing the issue on a disposable copy.
- If a new migration later fails, use the migration's tested downgrade only when it is data-safe; otherwise restore the pre-migration backup and investigate.

## 3. Runtime cutover task breakdown

| Task | Expected files | Implementation scope | Tests and acceptance criteria | Rollback / stop conditions | Commit message | Dependency |
| --- | --- | --- | --- | --- | --- | --- |
| 0.4.1 — schema-state diagnostics and parity checker | Add `backend/tools/schema_parity.py`, `backend/tests/test_schema_parity.py`, and focused operator documentation under `docs/architecture/` | Read-only metadata/inspector comparison and explicit target-path validation. No API integration and no stamping. | Temporary fresh, matching, missing-column, unexpected-table, and invalid-version SQLite fixtures. It must never open `redsea.db` by default. | Remove the new diagnostic file if it proves unable to distinguish expected SQLite reflection differences. Stop on any write, unknown target path, or SQL Server connection. | `feat: add schema parity diagnostics` | Baseline migration. |
| 0.4.2 — explicit migration/bootstrap command | Add `backend/tools/db_bootstrap.py`, `backend/tests/test_db_bootstrap.py`, focused operator documentation, and the minimal `alembic/env.py` explicit-target hook | One explicit command that validates an operator-provided target then runs `alembic upgrade head` for fresh databases. It must not be called from API imports. | Fresh temporary SQLite becomes current/head; invalid or existing un-stamped target is rejected with a clear error; API remains unchanged. | Revert the new command only; stop if it can fall back to `redsea.db` implicitly. | `feat: add explicit sqlite database bootstrap command` | 0.4.1. |
| 0.4.3 — adopt/stamp a disposable existing SQLite copy | Add `backend/tools/db_adopt.py`, `backend/tests/test_db_adopt.py`, and focused adoption documentation | Require backup proof and an all-green parity report before allowing `stamp a4fcbd8f8388` on an explicitly named disposable copy. | Matching copy stamps and becomes `current --check-heads`; mismatches, bad integrity, and unknown revisions fail without modifying the copy. | Restore the copy from backup; stop on any operation against `redsea.db`. | `feat: add guarded sqlite database adoption command` | 0.4.1 and 0.4.2. |
| 0.4.4 — retire runtime ALTER TABLE compatibility loop | Modify `backend/main.py`; add/update a focused startup/schema test | The generic startup repair loop that inspected every modeled table and added missing columns with raw `ALTER TABLE` is retired. Alembic is the schema-change authority; fresh SQLite uses `backend.tools.db_bootstrap`, and a matching existing SQLite database uses parity verification followed by `backend.tools.db_adopt`. `Base.metadata.create_all()` remains temporarily until Task 0.4.5. No startup schema-version guard is active yet. | Existing adopted copy and fresh migrated temp DB start without ALTER calls; an outdated database is not repaired automatically and may fail naturally when application code uses a missing column. | Revert this commit to restore compatibility behavior; stop if any supported workflow requires silent startup repair. | `refactor: retire runtime alter table compatibility logic` | 0.4.3 and a validated repair migration for any discovered drift. |
| 0.4.5 — retire runtime `create_all()` | Modify `backend/main.py`, `backend/tests/test_check_control.py`, `backend/tests/test_api_check_control.py`, and migration test helpers | Replace test setup that relies on import-time schema creation with `alembic upgrade head` against test-owned databases, then remove `Base.metadata.create_all()` from API import. | Fresh bootstrap command works; API starts after migration; API import against an empty DB fails clearly or is prevented; all tests own temporary DBs and migrate them. | Revert this commit; stop if any API/worker/test startup path relies on implicit creation. | `refactor: require alembic-managed schema at startup` | 0.4.2 and 0.4.4. |
| 0.4.6 — startup version check | Add `backend/schema_version.py`, modify `backend/main.py`, and add focused tests | At API startup, compare database revision to Alembic heads and refuse service with an actionable message when outdated or unknown. No migration execution. | Current temp DB starts; base/outdated/unknown revision DB fails deterministically; no DDL is emitted. | Revert the check if false positives appear; stop if multi-head handling is ambiguous. | `feat: enforce database schema version at startup` | 0.4.5. |
| 0.4.7 — workflow validation | Add `backend/tests/test_migration_workflows.py`; update only test fixtures as required | Validate fresh install, existing-copy adoption, upgrade path for each future revision, and API/worker startup with no runtime DDL. | CI runs all workflows on temporary SQLite; clean install and adopted-copy paths pass; `redsea.db` hash is unchanged. | Revert test-only changes if fixtures leak host paths; stop release if either workflow fails. | `test: cover database migration workflows` | 0.4.1–0.4.6. |

## 4. Environment ownership matrix

| Environment | Who runs migrations and when | `create_all` / runtime DDL | Startup when schema is outdated | Recovery |
| --- | --- | --- | --- | --- |
| Developer, fresh SQLite | Developer runs explicit bootstrap/migration command before API. | Disallowed after Task 0.4.5. | API refuses to start after Task 0.4.6. | Delete only the confirmed disposable DB and bootstrap again. |
| Developer, existing SQLite | Developer runs diagnostics, backup, then guarded adoption/stamp; never automatic. | Disallowed after cutover. | Refuse start until parity/adoption is completed. | Restore timestamped backup and investigate on a copy. |
| Automated tests | Test fixture runs Alembic against a per-test or per-class temporary SQLite target. | Never allowed; tests must not use host `redsea.db`. | Test fails with clear schema-state output. | Dispose temporary DB and recreate it. |
| Staging SQL Server | CI/CD migration job or authorized DBA runs migrations before application deployment. | Never allowed. | API/worker deployment blocked by version check. | Restore database backup or apply a tested repair/downgrade plan. |
| Production SQL Server | Authorized deployment principal/DBA runs migrations in a controlled window before API/worker rollout. | Never allowed. | API/worker must fail closed with an actionable version mismatch. | Restore verified backup; use tested rollback only when data-safe. |
| Worker process | Does not run migrations; starts only after deployment migration and API version verification. | Never allowed. | Refuses or is not deployed against an incompatible schema. | Stop worker, recover DB via deployment procedure, redeploy matching worker. |
| API process | Does not run migrations; performs version check only after Task 0.4.6. | Never allowed. | Refuses service before serving requests. | Stop API, repair/restore database, migrate explicitly, restart. |

## 5. SQL Server preparation risk register

No SQL Server connection or validation occurred in this task. Every item below remains a preparation requirement before production adoption.

| Risk | Status | Required validation or action |
| --- | --- | --- |
| `String(length)` mappings and maximum lengths | Requires disposable SQL Server test | Apply baseline to disposable SQL Server and inspect generated types and lengths. Confirm business requirements for non-Unicode versus Unicode storage. |
| Unicode requirements | Requires model change decision | Current models use `String`/`Text`, not explicit `Unicode`/`UnicodeText`. Test Arabic and other non-ASCII values; change models only in a future schema-hardening revision if requirements demand Unicode types. |
| JSON mapping | Requires disposable SQL Server test | SQLAlchemy's SQL Server dialect supports JSON-formatted data, but the exact generated storage/query behaviour must be inspected using the project versions. |
| Enum mapping (`jobstatus`, `uploadkind`, `approle`) | Requires disposable SQL Server test | Verify the generated column types, allowed values, null handling, and downgrade behaviour; SQL Server does not provide a PostgreSQL-style native enum type. |
| Timezone-aware `DateTime` | Requires disposable SQL Server test | Insert/read timezone-aware values and inspect rendered DDL; confirm the desired `DATETIMEOFFSET`/precision semantics. |
| Boolean mapping | Requires disposable SQL Server test | Validate nullable `Boolean` columns render and round-trip as intended, including no implicit unwanted check constraints. |
| Constraint and index-name limits | Confirmed safe for current names | Current generated names are materially shorter than SQL Server's 128-character identifier limit. Recheck this for every future longer table/column name. [Microsoft identifier limits](https://learn.microsoft.com/en-us/sql/relational-databases/databases/database-identifiers?view=sql-server-ver17) |
| Multiple cascade paths | Requires disposable SQL Server test | Current FKs do not specify cascade actions, but validate generated DDL and future relationship changes because SQL Server can reject conflicting cascade paths. |
| pyodbc configuration | Requires disposable SQL Server test | Validate installed driver name, authentication mode, certificate policy, connection string escaping, and pool behaviour with the actual deployment identity. |
| Transactional DDL | Requires disposable SQL Server test | Test baseline upgrade, downgrade, and failure recovery with the exact SQL Server edition and pyodbc driver. |
| Migration locking/concurrency | Unknown | Define one migration runner, deployment lock/maintenance procedure, and a no-concurrent-startup rule before staging. |
| Schema ownership/default schema | Requires migration adjustment or deployment configuration | Confirm principal default schema and ensure Alembic targets the intended schema; current models do not declare one. |
| Database permissions | Requires disposable SQL Server test | Migration identity needs controlled DDL rights; API/worker identities should receive only required runtime DML rights after cutover. |

References: [Alembic command API](https://alembic.sqlalchemy.org/en/latest/api/commands.html), [Alembic SQLite batch-migration notes](https://alembic.sqlalchemy.org/en/latest/batch.html), [SQLAlchemy SQL Server dialect](https://docs.sqlalchemy.org/en/21/dialects/mssql.html), and [Microsoft SQL Server capacity limits](https://learn.microsoft.com/en-us/sql/sql-server/maximum-capacity-specifications-for-sql-server?view=sql-server-ver16).

## Recommendation

Start **Task 0.4.1 only**. Build a read-only schema parity diagnostic that accepts an explicit SQLite target and has no fallback to `redsea.db`. Do not remove `create_all()` or the runtime ALTER loop until the diagnostic and disposable-copy adoption workflow prove that the baseline represents the existing schema.
