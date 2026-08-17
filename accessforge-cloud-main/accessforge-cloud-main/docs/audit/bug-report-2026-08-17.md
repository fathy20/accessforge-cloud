# Bug Report — 2026-08-17 (Phase 2, Deliverable 1)

Scope: branch `fix/crew-hours-heavy-airport-rules` @ `cdb6762` (the most complete
code line). **No fixes applied** — every finding awaits an owner ruling. Every
file:line was verified against the working tree on the date above. Disciplines
are labeled per finding (security / database / API contract / observability /
production-readiness / correctness); no external reviewer skills were used —
these reviews were performed manually under those disciplines.

Already-tracked debt (durable jobs, relational job outputs, localStorage
tokens, history secrets, MCP_Memory tree merge) lives in `TECHNICAL_DEBT.md`
and is not re-listed.

Severity counts: **0 critical · 0 high · 7 medium · 7 low · 2 info** — the
session's earlier P0/P1 burn-down (authz gates, token stamps, path traversal,
response shapes) is why nothing critical remains.

---

## M-1 · correctness / production-readiness — Copilot's single-day fetch can miss a cross-midnight return leg

- **Where:** `backend/copilot/local_answers.py:173` (`fetch_report(period.start, period.end)` — one UTC day for "RSX431 on DATE" questions); `backend/statistics/crew_hours/domain.py:32,50` (`is_operating` excludes **only PSN**; `operating_crew_set` built from it); `domain.py:144–146,170` (duty grouping requires *identical* PSN-only crew sets and break < 4h).
- **What is wrong:** the MCP fetch trims rows back to the requested period after duty attribution. A return leg that *starts* on the next UTC day stays in a day-N fetch **only if** duty grouping connects it — which requires identical PSN-only crew sets. If the legs differ by a PAD/OBS rider (exactly the RSX6081-style case), grouping fails, the return leg is attributed to day N+1 and dropped from the day-N fetch — so the Copilot's STEP 4 never sees the neighbour and answers **No**, while the month-window report answers **Yes**.
- **Repro:** rows: leg A day N 20:00–23:30 crew {C1,C2,PAD-P1}; leg B day N+1 00:30–04:00 crew {C1,C2}; ask the Copilot about leg A with a real fetcher (not the test lambda, which ignores dates). The committed cross-consistency test cannot catch this — its `fetch_report` returns all rows regardless of period.
- **Severity:** medium. **Blast radius:** Copilot Heavy answers only, narrow conditions (cross-midnight return + rider-set difference); report unaffected.
- **Proposed fix:** widen the Heavy-intent fetch to `period.start − 1 day … period.end + 1 day` (rows are only *added* to the STEP-4 index; the answer still targets the asked flight). The alternative — aligning duty grouping's crew set with STEP 4's — is a **rule change to the 2026-08-09 parity ruling for totals attribution and needs your ruling; not proposed**.

## M-2 · correctness (duplicated rule) — two "operating crew set" definitions, both approved, nowhere distinguished

- **Where:** `domain.py:32` (`is_operating`: PSN-only — the 2026-08-09 parity ruling, governs **numeric totals & duty attribution**) vs `unknown_resolver.py` `operating_crew_codes` (PSN+PAD+OBS/OBS2/STB — the 2026-08-17 FIX-3 ruling, governs **STEP-4 crew comparison**).
- **What is wrong:** nothing, *individually* — each is owner-ruled for its purpose. But they share the name "operating crew" and no code or doc states they are deliberately different; this is precisely the seed pattern that produced `heavy.py` vs `cabin_heavy.py`. M-1 is the first interaction bug.
- **Severity:** medium (preventive). **Blast radius:** future contributors.
- **Proposed fix (behavior-preserving):** rename to `totals_crew_set` / `rotation_crew_codes` (or equivalents), add a cross-reference comment in both files, and add the distinction to the manual's `business-rules.md`. No rule changes.

## M-3 · observability — the GraphQL executor throws away LEON's error body

- **Where:** `backend/statistics/crew_hours/graphql.py:60–62` — non-2xx → `LeonResponseError(f"LEON GraphQL returned HTTP {status}")`, body discarded.
- **What is wrong:** LEON puts the actionable text in the body (`"Argument 'timeInterval' validation failed with reason 'Interval length out of bounds'"` — this session's live probe diagnosis required a hand-rolled raw request because the executor hid it).
- **Repro:** any LEON 400; the exception carries the status only.
- **Severity:** medium. **Blast radius:** every LEON GraphQL failure becomes undiagnosable from logs.
- **Proposed fix:** parse `errors[].message` from a JSON body (bounded length, no headers/tokens) into the exception text; keep HTML bodies summarized to their `<title>`.

## M-4 · observability — Copilot failure logs carry only the exception type

- **Where:** `backend/copilot/router.py:33,88,106` — `logger.warning("Copilot ask failed (%s).", type(exc).__name__)`.
- **What is wrong:** the client-facing plain-status mapping is right, but the *server* log drops the message too — a `LeonResponseError` logs as just "LeonResponseError". Combined with M-3, operators get nothing.
- **Severity:** medium. **Proposed fix:** log `str(exc)` server-side (LEON messages contain no credentials; the transport already strips sensitive headers).

## M-5 · production-readiness — no rate limit or cache on LEON-expensive endpoints

- **Where:** `backend/statistics/crew_hours/router.py` report/export and `backend/copilot/router.py` ask — each request fires live LEON traffic (a month report = 1 MCP call + 1 FTL call + ~5 flight-list chunks; measured this session).
- **What is wrong:** a user holding refresh (or the UI's polling patterns) multiplies upstream load with zero throttling and zero caching; LEON already rate-limits (`LeonRateLimitError` exists), so bursts degrade the module for everyone.
- **Severity:** medium. **Blast radius:** crew-hours availability, LEON quota.
- **Proposed fix:** short-TTL in-process cache keyed by (period, position) for the report; per-user cooldown on copilot ask. Needs no schema change.

## M-6 · observability — `/health/ready` is blind to LEON

- **Where:** `backend/main.py:150–156` — DB connectivity + migration state only.
- **What is wrong:** LEON degradation (auth failure, rate limiting, schema rejection) is invisible to monitoring; `join_health`/`cabin_trainee_detection` exist only inside report responses.
- **Severity:** medium. **Proposed fix:** an optional `/health/leon` (or a `leon` block in ready, behind a flag) reporting last-known token/report status without making live calls per probe.

## M-7 · security (threat model) — project creation is open to every authenticated role

- **Where:** `backend/project_routes.py:48–49` — `POST ""` guarded by `get_current_user` only; the UI offers creation to engineer+ (`src/routes/_authenticated/projects.tsx:34`).
- **What is wrong:** a `guest`/`viewer` can create projects via the API. Documented as a known looseness in `MCP_Memory/api/projects.md`; escalating it here for an actual ruling.
- **Severity:** medium-low (no data exposure; content pollution + audit noise). **Proposed fix (if ruled):** role gate (engineer/admin/super_admin) mirroring the UI — one dependency + one test.

## L-1 · api-contract — pagination inconsistency across list endpoints

- **Where:** `backend/main.py:334` uploads `limit(100)` hardcoded; `main.py:229` notifications `limit(50)` hardcoded; jobs has `limit` (bounded) but no `offset`; projects has the full contract.
- **Severity:** low. **Proposed fix:** extend the projects pagination contract (`limit`/`offset`, bounded, stable ordering) to uploads/jobs/notifications; additive.

## L-2 · api-contract — creation endpoints return 200 instead of 201

- **Where:** `backend/main.py:259` (`POST /api/uploads`), `backend/project_routes.py:48` (`POST /api/projects`). Admin user creation already returns 201 — inconsistent.
- **Severity:** low. Fix additive; frontend checks `res.ok`, unaffected.

## L-3 · api-contract — upload delete reports 500 after a committed partial success

- **Where:** `backend/main.py` `delete_upload` — DB row deleted + committed, then file-unlink failure returns HTTP 500 with "metadata was removed but the artifact file could not be removed".
- **What is wrong:** 500 for a state the server *committed* misleads clients into retrying a delete that can never succeed again (404 on retry). **Severity:** low. **Proposed fix:** 200 with a `filesystem: "failed"` field (additive), or 207-style status; keep the audit row.

## L-4 · database — N+1 on `/api/admin/users`

- **Where:** `backend/models.py:107` (`roles` relationship, default lazy) + `backend/admin_routes.py:141` (`_role_values(user)` inside the per-user loop) — one roles query per user row.
- **Severity:** low (admin-only, tens of users). **Proposed fix:** `selectinload(User.roles)` on that query.

## L-5 · correctness — report default dates use server-local time

- **Where:** `backend/statistics/crew_hours/service.py:68` — `date.today()` fills empty from/to; all report data is UTC.
- **What is wrong:** near midnight in a non-UTC server timezone the default month/day boundary is off by one day vs the data. **Severity:** low. **Proposed fix:** `datetime.now(timezone.utc).date()`.

## L-6 · duplicated logic — four parser/helper families duplicated across modules

- **Where:** `_optional_int` ×2 (`local_answers.py:305`, `service.py:609`); `_optional_string`/`_text` ×3 (`crew_context.py:283` — **raises** on non-str, `service.py:605` and `local_answers.py:541` — return None: divergent semantics under one concept); tag parsing ×2 (`local_answers.py:380` `_tags_from_row`, `crew_context.py:330` `_flight_tag_labels`); int-nid normalizers with raise-vs-None splits (`crew_context.py` `_normalize_flight_nid` raises, `augmented.py` `_normalize_tr_nid` returns None).
- **Severity:** low today; this class of drift caused the Heavy divergence. **Proposed fix:** one `crew_hours/parsing.py` with the strict and lenient variants explicitly named; Deliverable-3 refactor material.

## L-7 · security-hygiene — the shadow env file `backend/.envpython`

- **Where:** `backend/.envpython` (holds LEON keys on dev machines) — never loaded by `backend/config.py` (which reads `.env`/`backend/.env` only).
- **What is wrong:** a config surface that looks live but isn't; it already contributed to the probe's "LEON_BASE_URL is required" dead-start this session, and it duplicates credentials in a second unmanaged file.
- **Severity:** low. **Proposed fix:** consolidate into `backend/.env` and delete the file locally (it is git-ignored; nothing to commit) + a line in the onboarding doc.

## I-1 · security (data sharing) — browser path sent to LEON as Wingman localContext

- **Where:** `src/components/app/AppLayout.tsx:19` (`window.location.pathname`) → `backend/copilot/wingman.py:318` (`localContext` in the LEON mutation).
- **What:** internal route paths flow to a third party. They contain no IDs today (verified route table), so **info** only — but any future route embedding an identifier starts leaking it. Note for the manual + a comment at the source.

## I-2 · watch-item — frontend `POSITIONING_TOKENS` (6 tokens) vs backend `POSITIONING_POSITIONS` (2)

- **Where:** `src/components/crew-hours/types.ts:70` vs `backend/statistics/crew_hours/positions.py:68`.
- **What:** deliberately different concepts (UI display filter vs operating-count rule). Not a bug — documented here so nobody "fixes" the mismatch and silently changes the count rule. Belongs in `business-rules.md`.

---

## Dead-weight inventory (input to Deliverable 2 — the deletion list; nothing deleted)

| Item | Where | Evidence |
|---|---|---|
| `minimum_required_cockpit` / `minimum_required_cabin` + `MINIMUM_*`/`DEFAULT_MINIMUM_*` | `positions.py:94–123` | zero callers outside their own file (repo-wide grep) |
| `_flight_nid_as_int` | `crew_context.py:260` | zero callers |
| `derive_heavy` wrapper | `heavy.py:188` | test-only callers; production uses `derive_heavy_detail`/facade |
| `positioning_crew` MCP column | `mcp_report.py:36` fetched; `service.py:560` "intentionally unused; semantics unverified" | fetched-but-unused payload |
| `journeyLog { … }` block in the shared flight query | `flight_query.py:48–57` | crew-context chunks fetch it and drop it (`_parse_crew_context_flights` keeps 7 keys); the only parser of it (`leon_client.fetch_flights`) has no production caller in the report path |
| `cabin_heavy.py` shim | whole module | scheduled deletion next release per ADR Decision 5 |
| `Job.logs` API exposure remnants | none — server-side only | keep (operator debugging) — listed to show it was considered |

## Escalations bundled in this report (rulings needed)

1. **M-1 fix choice**: widen the Copilot Heavy fetch window (safe, proposed) vs touching duty-grouping's crew set (rule change — needs your explicit ruling).
2. **M-7**: should `POST /api/projects` be role-gated to match the UI?
3. **M-2 renames**: approve the behavior-preserving rename pair for the two crew-set concepts.
