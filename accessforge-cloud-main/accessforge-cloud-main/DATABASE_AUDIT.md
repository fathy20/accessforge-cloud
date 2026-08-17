# Database Audit — 2026-08-17

Dialects: SQLite (development/test), SQL Server via pyodbc (production).
Alembic owns the schema; `create_all` is restricted to SQLite dev/test.

## Schema assessment

11 application tables, String(36) UUID PKs, a pinned naming convention
(`ix_/uq_/ck_/fk_/pk_`), CHECK constraints backing every enum column, and
timezone-aware timestamps (SQLite stores them naive; all comparisons are
generated per-request from the same source, so this is consistent).

## Migration chain (single head, walkable, tested)

```
a4fcbd8f8388  baseline (current schema at adoption)
c7e4a1b93d42  RBAC foundation (permissions, role_permissions, checks, backfills)
d9f0a2b7c4e1  account lifecycle fields
e1a2b3c4d5f6  module readiness
f7a8b9c0d1e2  secure upload artifacts (sha256, scan_state, retention)
b8c9d0e1f2a3  users.status NOT NULL + server default
c9d0e1f2a3b4  integrity indexes + uniqueness + project fields   ← added by this audit
```

Gates that hold for every revision (see `test_alembic_migrations.py`):
clean upgrade from an empty DB, real downgrade, deterministic re-upgrade,
**empty autogenerate diff** against the models, stable constraint names,
no SQLite-only syntax in the offline SQL Server script. The new revision was
additionally rehearsed offline against SQL Server in both directions.

## Problems found and fixed (revision `c9d0e1f2a3b4`)

1. **No index on any hot filter column.** Every list endpoint filters by a
   user-shaped FK, and audit reads order by `ts` — all unindexed (SQL Server
   does not index FKs automatically). Added: `jobs.user_id`, `uploads.user_id`,
   `notifications.user_id`, `audit_log.user_id`, `audit_log.ts`,
   `module_access.user_id`, `module_access.module_id`, `user_roles.user_id`,
   `projects.owner_id`.
2. **`user_roles` allowed duplicate (user, role) rows.** The last-super-admin
   guard counts assignment rows, and role updates delete-then-insert — a crash
   between the two, or any direct insert, could distort the arithmetic.
   Unique index added after deterministic dedupe (lowest id wins).
3. **`module_access` allowed duplicate (user, module) rows**, making the
   per-user disable flag ambiguous. Same treatment.
4. **`projects` lacked `tail_number`/`station`** — the UI has always submitted
   them; they were silently dropped. Columns added and wired end-to-end.
5. **The Alembic head was hardcoded in six places** (tools + tests); every new
   migration required a synchronized edit. All six now derive it from the
   script directory (`backend/tools/alembic_head.py`).

## Query-layer findings fixed elsewhere in this audit

- Output-download authorization scanned **all** of a user's jobs in Python;
  now restricted to `status == done` (the real fix — a relational outputs
  table — belongs to the durable-jobs slice, see TECHNICAL_DEBT.md).
- Unbounded `limit` parameters on jobs/audit listings — bounded.
- Job `logs` JSON column grew without bound and was rewritten wholesale on
  every append — bounded to the newest 200 entries.
- `started_at`/`completed_at` were never populated — now written.

## Remaining observations (not defects requiring immediate action)

- `user_id` FK columns are nullable in several tables where a row without an
  owner is meaningless (uploads, jobs). Tightening requires a data audit on
  the production SQL Server first; deferred deliberately.
- `role_permissions` lookups are served by the existing
  `uq_role_permissions_role` composite unique (role prefix) — no extra index
  needed.
- `get_effective_permissions` runs one join per request (twice on module
  listing); at this scale (≤ dozens of permissions) caching would be
  premature.
- Dev-machine drift: the local `redsea.db` predates `ck_users_status` (it was
  created by `create_all` + stamp). Rebuild via `python -m backend.tools.db_bootstrap`
  when convenient; a backup exists (`redsea.db.bak-pre-b8c9d0e1f2a3`, now
  git-ignored).

## Test-database safety

`conftest.py` + `validate_test_database_url` refuse any test target that is
not an in-memory or temp-directory SQLite file, and explicitly refuse
`mssql`/`pyodbc`/dev-database URLs. Verified intact.
