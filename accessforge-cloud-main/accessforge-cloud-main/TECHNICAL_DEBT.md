# Technical Debt Register — 2026-08-17

Ordered by priority. Each item is deliberate, known, and scoped — none is a
silent omission. Items fixed during the 2026-08-17 audit are not listed; see
SYSTEM_AUDIT.md for those.

## P1

### 1. In-process job execution (durability, isolation, timeouts) — LANDED 2026-09-03, one item open
- **Was**: jobs ran via FastAPI `BackgroundTasks` — lost on restart, no
  cancellation, no timeout, heavy OCR could starve the API process.
- **Now**: `JOB_EXECUTION_MODE=worker` + `python -m worker.runner`
  (migration `d1e2f3a4b5c6`). SQL-backed queue on `jobs`, atomic claim with a
  per-claim `lease_token`, every worker write fenced on it, heartbeat + stale
  reclaim (`JOB_MAX_ATTEMPTS` cap), killable child process per job with
  process-tree kill on both platforms, cancel and retry endpoints, graceful
  release on shutdown, at-least-once stated in the docs. Tests:
  `backend/tests/test_job_queue.py`. Inline mode remains the local default.
- **Still open**: claim/locking has only been exercised on SQLite. Run the
  suite's queue tests and a two-worker soak against a real SQL Server before
  relying on it in production; add `READPAST` hints only if contention shows.
  Outputs are published after the files are persisted, so a crash in between
  leaves orphan files (closes with #2).
- **Complexity**: S (verification on SQL Server).

### 2. Job outputs have no relational home
- **Problem**: outputs live inside `jobs.output_refs` JSON; download
  authorization string-matches storage names across the user's completed jobs.
- **Impact**: O(jobs×outputs) per download; no FK integrity; awkward audits.
- **Solution**: `job_outputs` table (job_id FK, storage_name unique, metadata),
  written at publish time. Natural part of the durable-jobs slice.
- **Complexity**: M.

### 3. Secrets in git history
- **Problem**: `.env` (JWT secret, `WORKER_HMAC_SECRET`, SQL and Supabase
  credentials) and `redsea.db` are reachable in history before `5be7448`.
  A live `.env` value was additionally treated as compromised on 2026-08-18.
- **`redsea.db` blob contents (inspected 2026-08-18, both historical
  versions):** dev-era data only — NO crew names, person codes, or flight
  records (no such tables exist in it). It holds 4 user accounts (bcrypt
  password hashes; dev/admin-style emails, one personal address), 2 PDF
  upload records, 5 completed task_extractor/task_stamping job rows, 8 module
  definitions; audit_log/projects/notifications empty. Exposure = those
  account credentials (hashes) + one personal email, all covered by rotation
  and dev-account password resets. Rewrite priority therefore stays
  *hygiene*, not data-breach response.
- **Impact**: anyone with repo access holds every historical credential.
- **Solution — sequence agreed 2026-08-18, in this order; do NOT reorder:**
  1. **Rotate** all of the above (in progress, owner). Once rotated, the
     history blobs are worthless and the rewrite is hygiene, not an emergency.
  2. **Close PR #5 and PR #6 first.** Never run the rewrite while PRs are
     open — it force-rebases every branch and orphans their heads.
  3. **Notify the frontend teammate BEFORE the rewrite** and agree the window:
     a force-pushed rewrite silently corrupts an existing clone (pulls appear
     to work while history has diverged). They must stop pushing until step 4
     is done.
  4. **Rewrite history** with `git filter-repo` (drop historical `.env` and
     `redsea.db`), then force-push and re-protect branches.
  5. **After the rewrite, the teammate deletes their clone entirely and
     re-clones fresh** — no pull/rebase of the old clone is acceptable; it
     would resurrect the pre-rewrite objects.
- This item stays OPEN until step 5 completes — ".env is gitignored/untracked
  today" is not grounds to close it; the exposure is historical.
- **Complexity**: S (coordination, not code).

## P2

### 4. Tokens in localStorage
- **Problem**: JWT in localStorage is readable by any successful XSS.
- **Solution**: httpOnly SameSite cookie + CSRF token; touches ApiClient, CORS,
  and every auth flow — do as one slice.
- **Complexity**: M.

### 5. `worker/toolkit.py` wraps the verbatim desktop file
- **Problem**: four handlers import `redsea_toolkit.py` (5,026 lines of
  desktop code) behind Tk stubs; roadmap item 10 says unwind this.
- **Solution**: extract the ~6 primitives handlers actually use
  (TcmIndexer, patterns, ocr_page_text, group_contiguous, expand_check) into a
  headless module with parity tests; keep the original file frozen for
  reference until app2 migration completes.
- **Complexity**: M–L (parity risk; the existing parity tests are the net).

### 6. DATABASE/FILE_UPLOAD dual-source is file-only
- **Problem**: every handler's `data_source == "db"` branch raises
  `NotImplementedError` (deliberate honesty).
- **Solution**: roadmap item 9 (maintenance data foundation) defines the DB
  source; do not fake it before the data model exists.
- **Complexity**: L.

### 7. `effectivity` and `utilization` have no business rules
- **Problem**: placeholders marked `discovery_required`.
- **Solution**: business discovery first — the standing instruction forbids
  inventing rules. Guarded by `test_module_readiness`.
- **Complexity**: unknown (business-bound).

### 8. Process-local login rate limiting
- **Problem**: the in-memory limiter (now bounded) does not span workers or
  restarts; persistent lockout is the true control.
- **Solution**: only worth shared state (DB counter or cache) if multi-worker
  deployment happens; revisit with the durable-jobs infrastructure.
- **Complexity**: S–M.

## P3

### 9. Retry/cancel buttons are stubs in the jobs UI ("not implemented yet") —
  wire them when durable jobs land (cancel is meaningless until execution is
  killable).
### 10. Backend suite takes ~4½ minutes, dominated by bcrypt in fixtures —
  a session-scoped low-cost CryptContext for tests would cut it substantially.
### 11. `notifications` are written by no code path (dead feature scaffold) —
  either wire producers (job completion is the obvious one) or drop the bell.
### 12. Frontend `any`-typed API payloads in several routes — introduce shared
  response types matching the now-explicit serializers.
### 13. `docs/architecture/*.md` (4 files) were untracked working documents —
  now committed; keep them current or fold them into ARCHITECTURE.md.
