# Backend audit

Audited 2026-08-16 against the repository only. Anything not verifiable from the repo
is listed under **Requires external confirmation** rather than guessed.

Not inspected, per instruction: `statistics/crew_hours/service.py`,
`statistics/crew_hours/heavy.py` (S5 pause), `statistics/crew_hours/token_provider.py`
(API-key auth path), and all Wingman code.

---

## 3a. Structure and layering

| File | Lines | Role |
|---|---|---|
| `backend/main.py` | 764 | App wiring, CORS, **16 routes defined inline** |
| `backend/auth.py` | — | `/api/auth` router, JWT, `get_current_user` |
| `backend/config.py` | — | Env loading, DB URL |
| `backend/database.py` | — | Session/engine |
| `backend/models.py` | — | ORM |
| `backend/storage.py` | — | Artifact storage with a governed path layer |
| `backend/admin_routes.py` | — | `/api/admin` |
| `backend/project_routes.py` | — | `/api/projects` |
| `backend/statistics/crew_hours/*` | — | The only module with a real service layer |
| `backend/copilot/*` | — | Router → service → client, added this session |

**Layering is inconsistent.** Two patterns coexist:

- **Layered (good):** `crew_hours` and `copilot` — `router.py` → `service.py` →
  client/provider, with a `Protocol` boundary and DI via `Depends`. Validation sits
  in Pydantic schemas.
- **Unlayered:** `main.py` holds 16 routes with business logic inline, including the
  upload path (`backend/main.py:180`) and the download path (`:592`). There is no
  service module for uploads/jobs; helpers like `_owned_output_artifact` (`:568`) are
  private functions in the route file.

**Validation** happens in three different places: Pydantic models (crew_hours,
copilot), hand-rolled checks inside route bodies (main.py), and the storage layer
(`storage.py` raises `PathSecurityError`, `UploadTooLargeError`,
`UnsupportedArtifactError`). Only the third is consistently enforced.

**Consequence for the migration:** app2's modules must not be added to `main.py`.
They should follow the `crew_hours`/`copilot` shape, which is already proven here.

---

## 3b. Correctness and risk

Severity: **CRITICAL** (exploitable/data loss) · **HIGH** (likely production
incident) · **MEDIUM** · **LOW**.

### Findings in the existing backend

| # | Severity | Finding | Evidence |
|---|---|---|---|
| B1 | **CRITICAL** | Live LEON refresh token committed to a file on disk in the repo tree. Value not reproduced here. | `backend/.env:2` — gitignored (`.gitignore:43`) and **not tracked**, verified via `git ls-files`. Risk is disclosure via backups/screenshare, not via git. |
| B2 | **MEDIUM** | `JWT_SECRET_KEY` present in the root `.env` in plaintext. Also gitignored. | `.env:12` |
| B3 | **MEDIUM** | No rate limiting anywhere. `grep` for `slowapi|limiter|ratelimit` → **0 hits**. Auth endpoints included, so credential stuffing is unthrottled. | repo-wide |
| B4 | **MEDIUM** | Env-load line logs at INFO before uvicorn configures logging, so it never appears. Cost hours of debugging this session. | `backend/config.py:34` |
| B5 | **LOW** | `passlib`/`bcrypt` version mismatch throws `AttributeError: module 'bcrypt' has no attribute '__about__'` on every startup. Trapped, hashing works. | observed in server log |

### Findings deliberately **not** confirmed as problems

Several risks I expected were **absent**. Reporting these as clean, with evidence,
because an audit that only lists problems is not trustworthy.

| Check | Result |
|---|---|
| Bare `except:` in backend | **0** (`grep -c "except:"`) |
| `except Exception: pass` | **0** |
| SQL injection | None found — all access is via SQLAlchemy ORM; no f-string SQL |
| Path traversal on download | **Mitigated**: `storage_basename()` (`storage.py:149`) + ownership check `_owned_output_artifact()` (`main.py:568`), which rejects when `storage_name not in {filename, requested_name}` (`main.py:577`) |
| Upload filename injection | **Mitigated**: `sanitize_original_name()` (`storage.py:202`), plus a typed `ArtifactType` allow-list and `UploadTooLargeError` |
| Unauthenticated routes | **None.** An initial scan flagged `copilot/router.py:64` and `:80`; on inspection this was a **false positive** — both use `current_user: UserDependency`, where `UserDependency = Annotated[User, Depends(get_current_user)]` (`router.py:29`). Corrected. |
| Module-level mutable caches in the backend | None found |

### Blocking operations in request handlers

| # | Severity | Finding | Evidence |
|---|---|---|---|
| B6 | **HIGH** | `CopilotService._await_answer` polls LEON in a loop with `time.sleep(1.0)` for up to **45 s** inside a sync request handler. Under load this exhausts the thread pool. | `copilot/service.py` `POLL_TIMEOUT_SECONDS = 45.0` |
| B7 | **HIGH** | Crew Hours report fetches the full MCP report synchronously in-request; observed multi-second latency on a 30-day window. | `/api/statistics/crew-hours/report` |
| B8 | **MEDIUM** | Only `BackgroundTasks` is available (2 uses). **No durable job queue** — `celery|rq|dramatiq` → 0 hits. `BackgroundTasks` dies with the process and cannot report progress. | repo-wide |

### Cross-user data leakage

No leakage found in the current backend. The download path is ownership-scoped
(`main.py:568–606`) and no request-independent caches were found.

**However**, every app2 module in bucket C introduces leakage if ported as-is —
`TARGET_MODULE`, `APP_INSTANCE`, the pickle index cache, and `self.*` used as session
state. See the inventory, §4 bucket C.

---

## 3c. Scale readiness

| Dimension | Score | Evidence |
|---|---|---|
| Multi-tenancy & data isolation | **Partial** | Per-user ownership enforced on downloads (`main.py:568`); no tenant/operator dimension in the schema. |
| Statelessness | **Partial** | Backend holds no globals; but storage is local-disk (`local_storage/` at repo root) rather than object storage. |
| Background job processing | **Not started** | 0 queue libraries. `BackgroundTasks` ×2 only. **Hard blocker for every app2 PDF/OCR module.** |
| Object storage | **Not started** | `local_storage/` directory present; `storage.py` abstracts paths but the backend is filesystem-based. Governance layer exists, so swapping is feasible. |
| DB pooling & indices | **Partial** | `create_engine` present (6 hits); `index=True` on 6 columns only. Unverified whether pool sizing is tuned. |
| Rate limiting | **Not started** | 0 hits. |
| RBAC granularity | **Partial** | Beyond a single admin flag: `AppRole` enum with `super_admin` (`admin_routes.py:63`), `user_roles` table, `role_permissions`, `permissions`, `module_access` tables exist in the DB. Richer than expected. Per-route enforcement not audited exhaustively. |
| Audit logging | **Partial** | `audit_log` table exists; coverage per action unverified. |
| Structured logging & error tracking | **Partial** | 8 `logging.getLogger` call sites; no structured/JSON logging, no Sentry-equivalent found. |
| Test coverage per module | **Partial** | 422 backend tests, but heavily concentrated in `crew_hours` and `copilot`. Upload/download/admin paths thinly covered. |
| CI/CD | **Not started** | No `Dockerfile`, `fly.toml`, `Procfile`, or CI workflow found. Only Cloudflare Workers config for the **frontend** (`.output/server/wrangler.json`). |
| Migrations | **Done** | Alembic present, 47 references, `alembic/` directory and `alembic.ini`. |

---

## Requires external confirmation

Not determinable from the repo:

1. **Deployment target for the backend.** No Dockerfile or platform config exists.
   This decides the Tesseract question (see the migration plan, §4c).
2. **Whether a Tesseract binary can be installed** in that target.
3. **Object storage availability** (S3/R2/Azure Blob) and credentials.
4. **Expected concurrency** — how many planners run OCR simultaneously.
5. **Whether `local_storage/` is on a persistent volume** in any current deployment.
6. **Retention policy** for uploaded maintenance PDFs (regulatory).
