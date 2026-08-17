# Deploy Checklist — Foundation (PR #4: codex/backend-dependency-manifest)

Execute in order. Do not skip step 1: migration `c9d0e1f2a3b4` **deletes rows**
(deduplication of `user_roles` and `module_access`) in addition to adding
`projects.tail_number` / `projects.station` and nine indexes.

## 1. Back up the database

Full backup of the production database, verified restorable, **before**
`alembic upgrade`. Record the backup label next to the deploy ticket.

## 2. Pre-migration duplicate audit (run and RECORD the output)

Know exactly what the dedupe will remove before it removes it:

```sql
SELECT user_id, role, COUNT(*) AS n
FROM user_roles GROUP BY user_id, role HAVING COUNT(*) > 1;

SELECT user_id, module_id, COUNT(*) AS n
FROM module_access GROUP BY user_id, module_id HAVING COUNT(*) > 1;
```

Empty results → the dedupe is a no-op. Non-empty → the migration keeps the
lowest `id` per group and deletes the rest; attach the query output to the
deploy record. (Semantics: only *exact* duplicate assignments are removed —
no role or module override is lost.)

## 3. Staging rehearsal (before production)

On a restored copy of the production database:

```bash
python -m alembic upgrade head        # applies through c9d0e1f2a3b4
# verify: app boots, /health/ready shows migration=current, spot-check logins
python -m alembic downgrade b8c9d0e1f2a3
python -m alembic upgrade head        # deterministic re-upgrade
```

All three steps must succeed cleanly. The offline SQL Server DDL for both
directions was rehearsed in review; the staging run is the live confirmation.

## 4. Team notice — one-time logout for everyone

`dea3443` binds tokens to the password stamp. Every token issued before this
deploy lacks the stamp claim and dies on its first request: **every user is
logged out exactly once and signs back in with unchanged credentials.**
Announce it before the deploy window to avoid a support wave. After that,
password changes/resets revoke sessions as designed.

## 5. CORS

Allowed origins come from `CORS_ORIGINS` (comma-separated exact origins;
check the deployed value with `grep ^CORS_ORIGINS .env`). Current on-prem
setup serves the frontend at `http://localhost:8080` (dev also uses `:5173`).
**Production refuses a wildcard** (`*` fails startup by design): any future
external hostname must be added to `CORS_ORIGINS` explicitly, then the
backend restarted.

## 6. Post-deploy verification

- `/health/ready` → `{"status":"ok", "migration":"current"}`.
- Log in, open Uploads/Jobs/Projects, download one artifact.
- Crew Hours report for the current month loads and `join_health` is `OK`.
- Audit log shows the deploy-window login events.
