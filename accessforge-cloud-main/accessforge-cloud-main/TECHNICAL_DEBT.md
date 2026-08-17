# Technical Debt Register — 2026-08-17

Ordered by priority. Each item is deliberate, known, and scoped — none is a
silent omission. Items fixed during the 2026-08-17 audit are not listed; see
SYSTEM_AUDIT.md for those.

## P1

### 1. In-process job execution (durability, isolation, timeouts)
- **Problem**: jobs run via FastAPI `BackgroundTasks` — lost on restart, no
  cancellation, no timeout, heavy OCR can starve the API process.
- **Impact**: reliability and DoS exposure; `queued` jobs orphan on crash.
- **Solution (already decided, adversarially reviewed)**: SQL-backed queue on
  the `jobs` table, separate `python -m worker.runner` process, atomic claim
  with lease/fencing generation, heartbeat + stale reclaim, killable child
  process per job (Windows process-tree kill), per-attempt staging + manifest
  publish, at-least-once semantics stated honestly. Test claim/locking against
  real SQL Server, not SQLite.
- **Complexity**: L (its own slice; design is settled).

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
- **Impact**: anyone with repo access holds every historical credential.
- **Solution**: rotate all of them; rewrite history with `git filter-repo`
  before widening repo access.
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
