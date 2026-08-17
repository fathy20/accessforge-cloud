# Architecture — AccessForge Cloud (REDSEA Toolkit Web)

## System overview

```
┌────────────────────────┐        ┌─────────────────────────────┐
│  Frontend (SPA)        │  HTTP  │  Backend (FastAPI)          │
│  TanStack Start/React  ├───────►│  backend/                   │
│  src/                  │ Bearer │  ├─ auth.py      (JWT, pwd) │
│  Vite, Tailwind, Radix │  JWT   │  ├─ rbac/        (grants)   │
└────────────────────────┘        │  ├─ main.py      (uploads,  │
                                  │  │   jobs, modules, notif.) │
        localStorage token        │  ├─ admin_routes.py         │
                                  │  ├─ project_routes.py       │
                                  │  ├─ statistics/crew_hours/  │──► LEON GraphQL
                                  │  ├─ copilot/                │──► LEON Wingman + MCP
                                  │  └─ storage.py   (artifacts)│
                                  └──────────┬──────────────────┘
                                             │ SQLAlchemy
                                  ┌──────────▼──────────────────┐
                                  │ SQLite (dev) / SQL Server   │
                                  │ Alembic owns the schema     │
                                  └─────────────────────────────┘
        worker/handlers.py  ← in-process module handlers (BackgroundTasks)
        worker/redsea_toolkit.py ← verbatim desktop logic behind Tk stubs
```

## Major components and responsibilities

| Component | Responsibility |
|---|---|
| `backend/auth.py` | Login, registration, password change, profile, JWT issuance/validation. Tokens carry a **password stamp** (`pwd` claim = `password_changed_at`) so any password change revokes all outstanding sessions. Shared password policy (12–72). Login timing is equalized against a dummy bcrypt hash. |
| `backend/rbac/` | `registry.py`: code-owned module + permission catalogue and per-role defaults. `permissions.py`: `get_effective_permissions`, `require_permission(s)()` FastAPI dependencies (default deny), sanitized `record_audit`. |
| `backend/main.py` | App wiring (lifespan seeding, CORS), uploads, jobs (create/list/get + in-process execution), module listing/visibility, notifications, output downloads. All endpoints serialize **explicit response shapes** — never raw ORM rows. |
| `backend/storage.py` | The only filesystem seam. Path containment (Windows-aware), streamed size enforcement, extension+MIME+magic-byte validation, SHA-256, unique server-side names, anchored storage root (`ARTIFACT_STORAGE_DIR` or project root). |
| `backend/statistics/crew_hours/` | LEON integration: config, transport (httpx), token provider (refresh→access), GraphQL executor, MCP report fetch, domain rules (Heavy/Augmented, cabin/cockpit), export workbook, REST router (gated by `crew_hours.view` / `.export`). |
| `backend/copilot/` | Wingman chat client (GraphQL contract incl. LEON's aliased-union quirks), local grounded answers from the MCP report, service that polls a thread to settlement, router gated by `crew_hours.view`. |
| `backend/tools/` | Operator CLIs: `db_bootstrap` (create+migrate), `db_adopt` (parity-check + stamp), `schema_parity`, `sync_registry`, `bootstrap_admin`, `alembic_head` (derives the single head — nothing hardcodes it). |
| `worker/` | Module handlers calling the preserved desktop toolkit primitives. `data_source == "db"` branches intentionally raise `NotImplementedError` (roadmap item). |
| `src/` | Routes under `_authenticated/` guard on `/auth/me`; `usePermissions` drives module visibility from `/api/modules`; `ApiClient` centralizes fetch + typed `ApiError` taxonomy; authenticated downloads stream via `fetchBlob`. |

## Authentication flow

1. `POST /api/auth/login` — rate-limited (bounded in-memory map + persistent
   `failed_login_count` lockout), bcrypt verify (dummy hash when the email is
   unknown), audited.
2. Token: HS256 JWT `{sub, pwd, exp}`; 7-day expiry; `pwd` is the password
   stamp. Every request re-validates user existence, stamp, and status.
3. `must_change_password` → frontend routes to `/reset-password`; the change
   endpoint returns a **fresh token** because the stamp change kills the old one.
4. Admin reset/create issue one-time temporary passwords and force
   `password_change_required`.

## Authorization flow

- Role → `role_permissions` rows (synced from code defaults) → effective
  permission set (union across the user's roles).
- Route gates: `require_permission("admin.users.manage")` etc. on admin routes;
  `require_crew_hours_view` / `require_crew_hours_export` on the report;
  `require_copilot_access` (= `crew_hours.view`) on Copilot.
- Module visibility (`_module_is_visible`): registry membership + projection
  parity + enabled + not hidden + no per-user disable + permission held. The
  same check gates job submission **and** job execution (defense in depth).
- Object ownership: uploads/jobs/notifications are owner-scoped in every query;
  projects are shared-visible but owner-or-admin for deletion.

## Job execution

`POST /api/jobs` validates module + input ownership, then runs the handler via
FastAPI `BackgroundTasks` (in-process). Timestamps (`started_at`/`completed_at`)
recorded; logs bounded to 200 entries and never returned by the API; outputs
persist through `storage.py` into governed storage with audit rows.
**Known limit:** jobs are lost on restart; the accepted durable-jobs design
(SQL-backed queue, separate worker process, lease fencing, killable child
processes) is documented in the roadmap and memory — deliberately not
implemented ad hoc here.

## Database architecture

- Alembic owns every schema change: baseline `a4fcbd8f8388` → … →
  `c9d0e1f2a3b4` (single head, derived programmatically).
- `create_all` is allowed only for SQLite dev/test; production refuses SQLite.
- String(36) UUID PKs; naming convention pinned (`ix_/uq_/ck_/fk_/pk_`);
  CHECK constraints back every enum column; FK/filter columns indexed;
  `user_roles(user_id, role)` and `module_access(user_id, module_id)` unique.
- Test safety: pytest refuses any non-temporary, non-SQLite target.

## External integrations (LEON)

- GraphQL (`{LEON_BASE_URL}/api/graphql`) with Bearer access tokens obtained
  from `LEON_REFRESH_TOKEN`; 31-day query chunking; masked-error and
  ErrorList quirks handled in the executor.
- MCP host (`LEON_MCP_URL`) serves the official Report Wizard rows the crew
  hours module and Copilot ground themselves on.
- Wingman chat is per-user in LEON; an API-key credential is rejected by LEON
  for chat resolvers — surfaced as a named identity error, not an outage.

## Important design decisions

1. **Code-owned registry, SQL projection** — a module/permission exists iff
   the code says so; drift fails closed.
2. **Password-stamped JWTs instead of a token blacklist** — no extra state,
   one DB read that the request already performs.
3. **No message broker** — SQL Server is the system of record; scale is tens
   of jobs/day on one Windows box (adversarially reviewed decision).
4. **Explicit serializers everywhere** — response shape is a contract, not a
   side effect of the ORM model.
5. **One filesystem seam** (`storage.py`) so containment and future governed
   storage have a single implementation.
6. **Honesty over completeness** — unfinished modules say so
   (`discovery_required`); LEON failures surface as failures.
