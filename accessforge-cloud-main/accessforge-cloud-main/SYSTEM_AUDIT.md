# System Audit — AccessForge Cloud / REDSEA Toolkit — 2026-08-17

## Executive summary

Full-repository forensic audit and remediation of the RedSea Airlines
engineering toolkit (FastAPI + SQL Server/SQLite backend, TanStack/React
frontend, LEON crew-data integration). The system arrived with a strong
security core in specific areas (governed artifact storage, RBAC foundation,
migration discipline) surrounded by significant gaps: **two P0 authorization
holes exposing crew data to permissionless users, sessions that survived
password resets, and six end-to-end broken user flows** the UI shipped against
endpoints that rejected or ignored them. All P0/P1 findings were fixed,
verified, and committed in six reviewed slices; the full backend suite
(450 tests) and all frontend gates (tsc, vitest 43/43, vite build) pass.

## What was found and fixed (by slice/commit)

### `bddcc5a` — Authorization gaps (P0)
- Crew Hours report + export and Copilot answered **any** authenticated
  session, including `guest` with zero grants → gated by `crew_hours.view`
  (+ `.export` for export) via a new composable `require_permissions()`.
- Copilot built LEON clients before auth ran and 500'd when unconfigured →
  auth first, plain 503 mapping.
- Projects: UI's delete button called a nonexistent endpoint → owner-or-admin
  DELETE added, audited; listing bounded and ordered.
- Copilot launcher hidden for users without the grant (server remains the gate).

### `dea3443` — Session integrity and password flows (P0/P1)
- JWTs survived password change/admin reset up to 7 days → tokens carry the
  `password_changed_at` stamp; any change revokes all sessions; change-password
  returns a fresh token.
- Registration accepted any password while change required 12 chars → one
  policy (12–72 bytes) everywhere.
- Login timing no longer discloses account existence (dummy bcrypt).
- Login limiter map bounded (was unbounded growth on attacker-chosen keys).
- **Broken flows repaired**: both password forms omitted `current_password`
  (guaranteed 422), login ignored `must_change_password`, signup pretended a
  pending registration was a live account, profile saved to a nonexistent
  `PUT /auth/profile`, and `/auth/me` lacked every field the profile page
  renders. All fixed end-to-end.

### `c45131d` — Response contracts and downloads (P1)
- Raw ORM rows leaked absolute storage paths (uploads) and full Python
  tracebacks (job logs) to clients → explicit serializers; logs/input_refs
  removed from the API; `limit` params bounded.
- Both UI download paths used `window.open` on Bearer-protected endpoints
  (guaranteed 401) → authenticated `fetchBlob` + object-URL save.

### `d22afd8` — Job execution correctness (P1/P2)
- `started_at`/`completed_at` never written; success path could dereference a
  vanished row; logs grew without bound; error messages unbounded; `sys.path`
  grew per job; cleanup failures went to `print`. All fixed; download
  authorization scans only completed jobs.

### `39dd777` — Database integrity (P1) — migration `c9d0e1f2a3b4`
- Nine indexes on previously unindexed hot filter columns; uniqueness (with
  dedupe) on `user_roles(user_id, role)` and `module_access(user_id,
  module_id)`; `projects.tail_number/station` (fields the UI always sent).
- Alembic head no longer hardcoded in six places — derived from the scripts.
- Rehearsed: clean SQLite upgrade/downgrade/re-upgrade, empty autogenerate
  diff, offline SQL Server DDL both directions.

### `fd434e8` — Configuration and startup (P1/P2)
- CORS: trimmed, de-slashed, wildcard refused in production (credentialed
  CORS forbids `*`), warned+dropped in dev.
- Artifact storage anchored to the project root (was cwd-relative — a server
  started elsewhere orphaned every artifact); `ARTIFACT_STORAGE_DIR` override.
- Registry seeding moved to a lifespan handler tolerant of concurrent
  multi-worker sync (was a deprecated `on_event` hook that raced).
- Upload requests capped at 20 files.

### Hygiene (this commit)
- Both `.gitignore`s repaired (corrupt first line; local_storage, DB backups,
  venv, pytest caches, agent scratch dirs, `.envpython` now ignored).
- `.env.example` documents every variable including the new knobs.
- Four untracked architecture documents committed.

## Verification

- Backend: full pytest suite green (450 passed, up from a 422-test baseline),
  including 28 new regression tests across 5 new test files
  (`test_endpoint_authorization`, `test_session_integrity`,
  `test_response_contracts`, `test_job_execution`, `test_cors_configuration`).
- Migrations: every revision gate in `test_alembic_migrations.py` green; new
  revision rehearsed offline for SQL Server (upgrade + downgrade).
- Frontend: `tsc --noEmit` clean, `vitest run` 43/43, `vite build` succeeds.

## What remains

See `TECHNICAL_DEBT.md` (prioritized, with decided designs where they exist).
Headlines: durable job execution (design settled, its own slice), relational
job outputs, secret rotation + history rewrite, httpOnly-cookie auth, desktop
toolkit extraction, and the deliberately-unimplemented modules that await real
business rules.

## Recommended next steps

1. **JOBS-1** (durable jobs) — the largest remaining reliability gap; design
   already reviewed and recorded.
2. Rotate historical credentials and rewrite git history before widening
   repository access.
3. Wire notifications to job completion (or remove the bell).
4. Move token storage to httpOnly cookies in one dedicated slice.
