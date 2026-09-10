# Deploy Readiness Plan — 2026-08-19

# Ready to deploy: **NO**

Four BLOCKERs. Each causes wrong data, data loss, or an unrotated credential —
none is cosmetic, and none is fixed by re-running the suite.

| ID | BLOCKER | One line |
|---|---|---|
| **B-1** | `module_access` dedupe silently flips per-user module authorization | Migration `c9d0e1f2a3b4` deletes rows by lexicographic UUID; the surviving `enabled` flag is arbitrary. Untested. The deploy checklist's audit query cannot detect it. |
| **B-2** | `cmp_tcm` check matching is a substring test | `check_code in cell_val` → check `A1` collects `A10`/`A11` tasks. Wrong maintenance cards, silently, today. |
| **B-3** | `cmp_tcm` never expands `CHECK_RELATIONS` | App2 fans `A10` → `[A1,A2,A5,A10]`; the web app generates the literal check only. **Fewer cards than the legacy system** for every related check. |
| **B-4** | Secrets still unrotated | `JWT_SECRET_KEY`, `WORKER_HMAC_SECRET`, SQL Server credentials remain compromised-in-history (`TECHNICAL_DEBT.md` #3 step 1 = "in progress"). A forged token for any user is possible until rotation lands. Plus a fresh LEON refresh-token exposure today (S-4). |

B-2/B-3 are BLOCKERs and not HIGH because **`readiness` does not gate anything**:
it is returned in the module payload (`backend/main.py:827`) and read by no
authorization or job-submission path (grep: no other `readiness` reference in
`main.py` or `rbac/permissions.py`). `cmp_tcm` is marked `under_validation`
(`backend/rbac/registry.py:113`) yet any permitted user can run it and receive
wrong output.

**Scope of this pass:** planning only. No code was edited, nothing was deleted,
nothing merged. Two suites were executed read-only for evidence (below).

---

## Verification baseline (run this pass, 2026-08-19)

| Check | Result |
|---|---|
| Backend suite | **507 passed in 1349.17s (22:29)** — `python -m pytest backend/tests/ -q`, 56 test files, zero failures |
| Frontend suite | **8 files / 48 tests passed in 40.74s** — `npx vitest run` |
| Clean Alembic upgrade on empty SQLite | **PASS** — all 7 revisions `a4fcbd8f8388 → c9d0e1f2a3b4` applied against a fresh temp DB |
| Alembic head count | **1** (linear chain, verified by `down_revision` walk) |

Two discrepancies against existing docs, recorded because they mislead:

- ~~`TECHNICAL_DEBT.md` #10 states the backend suite takes "~4½ minutes".
  Measured 22m 29s — 5× the documented figure.~~ **RETRACTED 2026-08-19.** The
  22m 29s was a cold run (no `__pycache__`). A warm re-run of the same suite
  took **4m 02s**, which matches the documented ~4½ minutes. The debt item's
  number is correct; my first measurement was not. Nothing to change in #10.
- The suite **cannot be run from the documented venv**. `backend/venv` has no
  `pytest` (`pip list`: fastapi/httpx/SQLAlchemy present, pytest absent) and
  `backend/requirements.txt` does not list it — nor does the version on
  `codex/backend-dependency-manifest`. The 507 passes above came from the
  system interpreter (Python 3.11, pytest 7.4.4). See **O-4**.

---

## 1. Module parity vs App2

Parity specification used: `docs/architecture/app2-module-inventory.md` (cites
`app2.py` line-by-line) and `app2.py` itself (4,944 lines, repo root).
`MCP_Memory/mapping/app2-vs-web.md` is a **4-line stub** and is not usable as a
spec — see **D-6**.

Readiness values below are from `backend/rbac/registry.py:59–183`.

| App2 module | App2 state (evidence) | Web impl | Registry readiness | Gap | "Done" means |
|---|---|---|---|---|---|
| Task Extractor | **BROKEN at runtime** — `_run_extract` (1615) calls `_find_related_tasks` (1650), `_extract_related_tasks_to_pdf` (1657), `_is_index_page` (1724) — none defined | `worker/handlers.py:34` | `under_validation` | No legacy reference exists to match. Web behavior is necessarily invented | Owner-approved written spec, then tests against it. **Parity is impossible by definition — say so, don't imply it** |
| Task Stamping | WORKING (`_tab_task_stamping` 2045; in-place `os.replace` 1970/2017) | `handlers.py:182` | `under_validation` | Legacy overwrote source PDFs; web must not. Stamp coordinates (§2.11) and Boeing-card regex (§2.9) unverified against web output | Byte-level comparison of stamped output vs App2 on the same input PDF |
| CMP / TCM | **WORKING, the core module** (`_generate_task_cards_indexed` 3425) | `handlers.py:328` | `under_validation` | **B-2, B-3** plus 3 more gaps (table below) | Same task set and same PDFs as App2 for a fixed Excel + TCM folder |
| TCM Indexing | WORKING (`TcmIndexer` 768) | `worker/redsea_toolkit.py` verbatim, via `toolkit.py` | `not_migrated` | Registry says not migrated, but the code **is** in use by `cmp_tcm`. Registry is wrong, or the label means "no standalone UI" — ambiguous | Decide what the label asserts; align it |
| Mail Merge | WORKING (`_mm_generate_document` 4099) | `handlers.py:426` | `under_validation` | `placeholder_index` (§2.3, 18 entries), legacy alias fan-out (661–672), LTR wrapping (§2.12), xlsx `definedNames` repair (3851) — none verified present | Field-for-field mapping test using §2.3 verbatim |
| Cover Merge | **DOES NOT EXIST** — no `_tab_cover_merge`; `covers_dir` is set to `None` once (979) and never again, so `_find_cover_for_task` (3555) always returns `None` | `handlers.py:409` | `under_development` | Web has an implementation with **no legacy counterpart**. Inventory §0.2 asks: dropped or unbuilt? | Owner ruling first (**Q-5**); no parity target exists |
| Check Control | **STUB** — `_tab_check_control` (2247) shows "UNDER DEVELOPMENT" and returns; `_load_check_csv` (2272) shows the dialog then still runs a thread against a never-created `self.tree_check` (a latent `AttributeError`) | `handlers.py:285` | `under_validation` | `handlers.py:284` comment claims it *"Mirrors RedseaApp._load_check_csv (L2272) + CHECK_RELATIONS expansion"* — **it mirrors a stub**. The rule is invented, provenance unknown | Escalated as **Q-3**: the comment is false and must not stand |
| Effectivity | STUB (`_tab_effectivity` 2122) | `handlers.py:267`, `db` branch raises | `discovery_required` | Greenfield — correctly labeled | Business discovery (debt #7) |
| Utilization | STUB (`_tab_utilization` 2303; `_load_util_csv` has `return` at 2351 with dead code 2353–2358) | `handlers.py:308`, `db` branch raises | `discovery_required` | Greenfield — correctly labeled | Business discovery (debt #7) |
| Crew Hours | **not an App2 module** | full stack | `available` | No parity obligation; governed by the ADR + `closed-questions.md` | Already met |
| `MiniLauncherManager` (144–447), package relations (1764–1820), hash stubs (2453/2472/2491), argparse CLI (4876) | Desktop-only / stubs | — | absent | Correctly not migrated (inventory bucket B) | n/a |

### `cmp_tcm` parity gaps in detail

Web implementation read at `worker/handlers.py:328–403`.

| # | App2 behavior (evidence) | Web behavior (evidence) | Effect |
|---|---|---|---|
| 1 | Exact match of the normalized check against **column 24** (`check_column = 24`, 3242) | `if check_code in cell_val or cell_val == check_code` (`handlers.py:363`) | **B-2.** `A1` matches cells containing `A10`, `A11`. Over-collects tasks |
| 2 | `expand_check` (449) fans the check to related checks via `CHECK_RELATIONS`, then generates cards for all of them (inventory §1.3) | No `expand_check` call anywhere in `cmp_tcm`. The function **exists in the worker** — `redsea_toolkit.py:460`, `return CHECK_RELATIONS.get(k, [k]) if k else []`, re-exported by `toolkit.py:25` — and `CHECK_RELATIONS` is imported at `handlers.py:21`, used only in a **comment** at `:284` | **B-3.** Under-generates: `A10` yields A10 tasks only, never A1/A2/A5. The fix is one call site, not a port |
| 3 | The `CMPISS03 R1` marker row must **exist** (regex 3220) or the extraction returns `[]` (3238). It is a **gate, not a slice** — `mpd_rsd_start_row` is assigned at 3222/3232 and **never read**, so App2 then scans all rows (3247) | No marker check at all; all rows scanned | App2 refuses a workbook lacking the marker; the web app processes it anyway. **Corrected 2026-08-19** — the first version of this row claimed App2 slices rows after the marker. It does not. Verified by `grep -n mpd_rsd_start_row app2.py` → 3 hits, all writes |
| 4 | Sheet whose upper-cased name contains `'MPD RSD'` (3191, 3376) | `pd.read_excel(excel_path)` → first sheet only (`:352`) | Wrong sheet silently on multi-sheet workbooks |
| 5 | `_expand_tasks_with_subtasks` (3082) probes `-01`..`-10` against the index (`range(1,11)`, 3109) | `indexer.find_related_subtasks(task)` — prefix match on the first two numeric segments (`redsea_toolkit.py`, App2 911) | Different rule; different subtask set |
| 6 | Column-24 guard `if df.shape[1] <= 24` (3398) | `if df_str.shape[1] > 24` (`:361`) — equivalent | No gap (recorded to show it was checked) |

### P-1 · `CHECK_RELATIONS` A7/A9/A11 self-exclusion ported verbatim
Severity: **HIGH** (BLOCKER if the owner rules the asymmetry is a typo)
Evidence: `worker/redsea_toolkit.py:121–140` is byte-identical to `app2.py:121–140`:
`"A7": ["A1"]`, `"A9": ["A1","A3"]`, `"A11": ["A1"]` — every other entry includes
itself (`"A5": ["A1","A5"]`).
What's wrong: nothing *yet* — `cmp_tcm` doesn't call `expand_check` (B-3). The
moment B-3 is fixed, running A7/A9/A11 generates **no cards for the check
itself**. Fixing B-3 without ruling on this ships a silent omission of
maintenance cards.
How it manifests: engineer requests A7, receives A1 cards only, no error.
Proposed fix: none — **owner decision Q-1**. Inventory question #1 asked this on
2026-08-17 and it is still open.
Owner decision needed? **YES** — see Q-1.
Test that will pin it: `expand_check("A7")` returns the ruled set, asserted per
check code from a table the owner signs off.
Blast radius: every generated task-card package.

### P-2 · `2000FC` unreachable from the default check list
Severity: LOW
Evidence: `app2.py:2528` default list omits `2000FC`, which `CHECK_RELATIONS`
defines and `check_patterns` (3004–3010) accepts.
Carried into the web app? **Unverified** — the web check list source was not
located this pass. Labeled `UNVERIFIED`; verify before acting.

---

## 2. Backend correctness

Status of every item in `docs/audit/bug-report-2026-08-17.md` (which lives only
on branch `docs/bug-report-2026-08-17` — see **PR-2**). Verified against the
working tree today; **not re-discovered**.

### Confirmed DONE and verified this pass

| ID | Commit | Verification |
|---|---|---|
| **M-1** cross-midnight Copilot fetch | `3e21014` | Report itself records the resolution; pinned by `test_heavy_cross_consistency.py::test_case_6_cross_midnight_return_with_rider_difference`. Suite green |
| **M-7** project creation authz | `0e2d405` | `_require_project_creator` at `backend/project_routes.py:51`, wired at `:64`. AppHarness tests assert viewer 403 create / 200 list, guest 403 |
| **L-5** UTC report defaults | `8dccf55` | `utc_today()` at `backend/statistics/crew_hours/domain.py:66`, feeding service defaults and Copilot relative periods |
| **M-2** two crew-set concepts | (in branch) | **Resolved as proposed**: `counts_in_totals` (`domain.py:32`, PSN-only, 2026-08-09 ruling) vs `rotation_crew_set` (`domain.py:55`, via `positions.crew_set_identity`) vs `unknown_resolver.rotation_crew_codes` (`:237`). Bidirectional "do NOT unify the two (M-2 ruling 2026-08-18)" comments at `domain.py:35–36` and `:60–62` |
| **I-2** positioning token mismatch | (in branch) | Renamed to `UI_POSITION_FILTER_TOKENS` (`src/components/crew-hours/types.ts:75`) with a comment at `:72–74` naming `positions.POSITIONING_POSITIONS` and warning against "fixing" it |

`closed-questions.md` items 1–8 were read and are **not re-opened** by anything
in this plan.

### Still open

### C-1 · M-3 — non-2xx LEON responses still discard the body
Severity: **MEDIUM** · **PARTIALLY FIXED — do not close it**
Evidence: `backend/statistics/crew_hours/graphql.py` — the `errors[]` path now
surfaces LEON's wording via `_describe_errors(errors)` (new since the report,
with a comment explaining why). But the **first** branch of `_parse_response` is
unchanged: `if response.status_code < 200 or >= 300: raise
LeonResponseError(f"LEON GraphQL returned HTTP {response.status_code}.")`.
What's wrong: the exact case M-3 cited — a **400** carrying `"Argument
'timeInterval' validation failed with reason 'Interval length out of bounds'"` —
is a non-2xx, so its body is still thrown away. The fix that landed covers
200-with-errors only.
How it manifests: any LEON 4xx/5xx logs as a bare status code.
Proposed fix: in the non-2xx branch, attempt the same JSON `errors[]` parse
before falling back to the status-only message; summarize HTML bodies to
`<title>`; bound length; never copy headers or tokens.
Owner decision needed? No.
Test: a stubbed transport returning 400 with a LEON error body; assert the
message text reaches the exception.
Blast radius: diagnostics only.

### C-2 · M-4 — Copilot failure logs carry only the exception type
Severity: MEDIUM
Evidence: `backend/copilot/router.py:33`, `:88`, `:106` — all three still
`logger.warning("… (%s).", type(exc).__name__)`.
Compounds C-1: a `LeonResponseError` logs as the literal string
`LeonResponseError`.
Proposed fix: log `str(exc)` server-side; client mapping unchanged.
Owner decision needed? No. Test: caplog assertion on the message.

### C-3 · M-6 — `/health/ready` is blind to LEON
Severity: MEDIUM
Evidence: `backend/main.py:149–167` — DB `SELECT 1` + `_migration_state` only.
Proposed fix: `/health/leon` (or a flagged `leon` block) reporting last-known
token/report status **without** live calls per probe.
Owner decision needed? Yes, minor — separate endpoint vs block in `ready`
(**Q-6**). Test: probe returns the cached status and issues no LEON request.

### C-4 · M-5 — no cache or throttle on LEON-expensive endpoints
Severity: MEDIUM
Evidence: `backend/statistics/crew_hours/router.py` and
`backend/copilot/router.py` reference `LeonRateLimitError` for **error mapping
only** (`router.py:61`, `copilot/router.py:58`); grep for
cache/ttl/cooldown/rate_limit in both files returns nothing else.
Proposed fix: short-TTL in-process cache keyed by (period, position) for the
report; per-user cooldown on `ask`. No schema change.
Owner decision needed? Yes — TTL length and whether a stale report is
acceptable (**Q-7**). Test: second identical request inside the TTL issues zero
LEON calls.

### C-5 · L-6 — four duplicated parser families
Severity: LOW · unchanged
Evidence: no `parsing.py` in `backend/statistics/crew_hours/`;
`_optional_int` ×2 (`service.py:614`, `copilot/local_answers.py:327`);
`_optional_string` (`service.py:606`) vs `_text` (`local_answers.py:569`);
`_normalize_flight_nid` **raises** (`crew_context.py:270`) vs
`_normalize_tr_nid` **returns None** (`augmented.py:263`).
Proposed fix: one module with strict/lenient variants explicitly named.

### C-6 · L-1 / L-2 / L-3 / L-4 — API-contract and query items
Severity: LOW · all unchanged
- L-1: `backend/main.py:229` notifications `limit(50)`, `:334` uploads
  `limit(100)`, both hardcoded, no `offset`. (`fix/projects-list-pagination`
  fixed projects only.)
- L-2: `POST /api/uploads` (`main.py:259`) and `POST ""` projects
  (`project_routes.py:63`) return 200; `admin_routes.py:316` returns 201.
- L-3: `delete_upload` still 500s after a committed partial success.
- L-4: no `selectinload`; `_role_values(user)` (`admin_routes.py:59`) called
  inside the per-user loop at `:141`.

### C-7 · I-1 — browser path sent to LEON as `localContext`
Severity: INFO · unchanged. Add the source comment and the manual note.

---

## 3. Database readiness (SQL Server)

Strong existing foundation — recorded so the plan does not re-litigate it.
`backend/tests/test_alembic_migrations.py` holds **22** gates, including empty
autogenerate diff vs models (`:266` — this is the schema-drift check),
real downgrade (`:283`), deterministic re-upgrade (`:296`), single head
(`:324`), naming-convention prefixes (`:374`), FK order safety (`:396`), and
six SQL-Server-specific DDL assertions: no SQLite-only syntax (`:440`), JSON →
`NVARCHAR(MAX)` (`:447`), Boolean → `BIT` (`:463`), tz-aware datetime →
`DATETIMEOFFSET` (`:472`), no IDENTITY on UUID string PKs (`:499`), user-facing
text precisely Unicode (`:504`). All green in the 507-pass run.

**Schema-vs-models drift: none.** Gated by `:266`.

### D-1 · `module_access` dedupe silently flips per-user module authorization
Severity: **BLOCKER (B-1)**
Evidence:
- `alembic/versions/c9d0e1f2a3b4_integrity_indexes.py:59–62`:
  `DELETE FROM module_access WHERE id NOT IN (SELECT MIN(id) FROM module_access GROUP BY user_id, module_id)`
- `id = Column(String(36), primary_key=True, default=gen_uuid)`
  (`backend/models.py:343`) — so `MIN(id)` is **lexicographic over a UUID**,
  i.e. arbitrary with respect to creation order.
- Duplicate rows are **not** interchangeable: `enabled`, `granted_by`,
  `created_at` (`models.py:346–348`).
- No test covers the dedupe: grep for `dedup|duplicate|DELETE FROM user_roles`
  in `test_alembic_migrations.py` returns nothing; no test references
  `c9d0e1f2a3b4`.
- `docs/deploy-checklist-foundation.md` step 2 audits with
  `SELECT user_id, module_id, COUNT(*) … HAVING COUNT(*) > 1` — **counts only**.
  It cannot reveal which `enabled` value survives.

What's wrong: a user explicitly **denied** a module can come out **enabled**
after the migration (or the reverse), decided by UUID sort order. The losing
row is deleted, so the original intent is unrecoverable post-deploy. The
migration's own comment calls this "one deterministic row (lowest id)" — it is
deterministic but **semantically arbitrary**, and the comment reads as if the
choice were safe.

How to reproduce: two `module_access` rows, same `(user_id, module_id)`,
`enabled` = 1 and 0; whichever row's UUID sorts lower survives.

Proposed fix: (a) replace step 2's count query with a full-row dump of every
conflicting group, run and recorded **before** the migration; and (b) make the
tie-break semantic rather than lexicographic. Which row wins is a business
question — **Q-2**.

Owner decision needed? **YES (Q-2).**
Test that will pin it: a migration test seeding conflicting `enabled` values and
asserting the ruled winner survives. This test does not exist today.
Blast radius: per-user module authorization for every user with a duplicate row.
Zero if production has no duplicates — which is exactly what the corrected
step-2 query establishes.

### D-2 · `user_roles` dedupe is safe — recorded to close it
Severity: n/a
Same `MIN(id)` pattern at `c9d0e1f2a3b4:55–58`, but `UserRole` carries only
`(id, user_id, role)` (`models.py:121–123`), so duplicate rows *are*
interchangeable and an arbitrary winner is harmless. No action.

### D-3 · Enum-column case sensitivity under SQL Server collation
Severity: LOW · **verify-only**
`role = Column(Enum(AppRole))` (`models.py:123`) compiles to VARCHAR + CHECK.
Under a case-insensitive server collation, `'ADMIN'` would satisfy a CHECK
listing `'admin'`, and `GROUP BY role` would fold case variants together —
changing what the dedupe removes and what the unique index enforces. The
application only ever writes enum values, so this requires hand-edited or
adopted data (`backend/tools/db_adopt.py` exists, so adoption did happen).
Proposed action: one audit query for case variants in `user_roles.role`. Do not
change code on the strength of this item.

### D-4 · Pre-migration audit does not check whether the added columns exist
Severity: MEDIUM
`c9d0e1f2a3b4:50–51` runs `op.add_column("projects", …)` for `tail_number` and
`station`. If the adopted SQL Server database already carries either column
(plausible given `db_adopt.py` and the `a4fcbd8f8388` "current schema at
adoption" baseline), `add_column` fails and aborts the migration mid-way.
Proposed fix: add an existence check to step 2 of the deploy checklist. Cheap,
and it converts a mid-migration abort into a pre-flight answer.

### D-5 · Deferred DB observations (from `DATABASE_AUDIT.md`, unchanged)
Nullable `user_id` FKs on `uploads`/`jobs` (tightening needs a production data
audit first); `get_effective_permissions` runs one join per request; local
`redsea.db` predates `ck_users_status`. All LOW, all already recorded — listed
so this plan is not read as discovering them.

### D-6 · Onboarding doc and seed script vs the real SQL Server setup
Severity: MEDIUM (docs), and the finding is **not** what it looks like
Evidence — the SQLite assumption is deliberate and matches the code:
- `docs/onboarding-local-setup.md` prescribes `DATABASE_URL=sqlite:///./redsea.db`
  and states "Do **not** set `SQL_SERVER_*` or `LEON_*` locally", under an
  explicit local-DB-only policy.
- `backend/config.py:46` `DEFAULT_DATABASE_URL = "sqlite:///./redsea.db"`;
  `:218–219` refuses SQLite when `APP_ENV=production`; `:98–106` assembles the
  SQL Server URL from `SQL_SERVER_*`. Both paths are real.
- `backend/tools/seed_dev_data.py` refuses unless `APP_ENV` ∈
  {development, test} **and** dialect == `sqlite`; idempotent via a marker
  account; creates no crew/flight rows. It **cannot** touch SQL Server.
- Neither file mentions Supabase.
- Onboarding step 3 (`alembic upgrade head`) **verified working** this pass.

So: no SQLite/Supabase confusion to correct. Two real gaps remain:
1. The doc never says the deployed system runs **SQL Server**. A new developer
   can reasonably infer SQLite is the system of record. One sentence pointing at
   the `SQL_SERVER_*` path and `docs/deploy-checklist-foundation.md` fixes it.
2. `.env.example:10–18` offers `DATABASE_URL` *or* `SQL_SERVER_*` with no hint
   which applies where.

**Both files exist only on `docs/dev-onboarding-and-deploy`** — absent from
`main` and from the current branch (`git ls-tree main | grep onboarding` →
empty). A teammate cloning `main` today has neither the doc nor the seed. That
is the actual risk, and it is **PR-3**.
Also: `MCP_Memory/mapping/app2-vs-web.md` is a 4-line stub presented as a
mapping document. Either fill it from `app2-module-inventory.md` or delete it —
as it stands it invites someone to trust it as the parity spec.

---

## 4. Supabase removal sweep

Runtime conclusion first: **nothing functionally depends on Supabase.**
`backend/`, `src/`, `worker/` source contain zero references; `requirements.txt`
has no supabase/postgres/psycopg; `package.json` has no `@supabase` dependency
and `node_modules/@supabase` does not exist. Auth is local JWT, storage is
`local_storage/`, DB is SQLAlchemy → SQLite (dev) / mssql+pyodbc (prod).
Deletion is safe. **Nothing was deleted in this pass.**

### (a) Dead config and code to remove

| Location | What | Note |
|---|---|---|
| `.env` (repo root) | `SUPABASE_PROJECT_ID`/`_PUBLISHABLE_KEY`/`_URL` + the `VITE_` triplet | Git-ignored, on-disk only. The file contains **nothing else** — deletable whole |
| `bun.lock` | `@supabase/supabase-js@^2.108.2` + 6 transitive `@supabase/*` | Orphaned lockfile: `package.json` has no such dep and `package-lock.json` has 0 hits. Two lockfiles for one project |
| `worker/__pycache__/{main,storage}.cpython-311.pyc` | Bytecode referencing `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, "Supabase Storage helpers" | Source `worker/storage.py` no longer exists. Git-ignored stale artifacts |
| `accessforge-cloud-main.zip` (19.8 MB) | Full Supabase-era snapshot: a `.env` with keys, the old `.pyc`s, `bun.lock`, 13 `MCP_Memory` docs | See **PR-1** — tracked on the trunk that merges first |
| `.lovable/plan.md:97` | "TanStack Query + Supabase Realtime للـ jobs والإشعارات" | Lovable scaffold artifact |

### (b) Docs now wrong

All under `MCP_Memory/`, which still presents Supabase as the architecture:
`system/architecture.md:3`; `system/tech-stack.md:3–4`; `backend/auth.md:2`;
`frontend/routing.md:3`; `modules/{check-control,task-extractor,task-stamping}.md`
(each lists "Supabase (Auth & DB)" and "Supabase Client (RPC & CRUD)");
`mapping/migration-plan.md:2`; `master-index.md:43,61`; `standards/supabase.md`
(whole file); `decisions/adr-002.md` ("Supabase as BaaS"), `adr-005.md`
("Supabase Auth will be used exclusively"), `adr-004.md:2` ("Supabase webhooks
may be used later" — also contradicts the agreed SQL-backed queue, debt #1);
`SECURITY_AUDIT.md:60` (lists Supabase keys among credentials awaiting rotation).

ADRs are historical records: 002/004/005 want **superseding notes**, not
deletion. The rest is rewrite-or-delete.

### (c) Still functionally depended on

**None.** Stated positively so the deletion pass is not blocked hunting for one.

### S-Sup · One security correction
The key committed as `SUPABASE_SERVICE_ROLE_KEY` in `f58477f` is **mislabelled**:
its JWT payload carries `"role":"anon"`, and it is byte-identical to the
publishable key still in the root `.env`. No privileged Supabase credential was
ever committed. Combined with project deletion, the Supabase entry in
`TECHNICAL_DEBT.md` #3 needs no rotation — only the other three credentials do
(**B-4**).

---

## 5. Security

Prior work verified in place, not re-derived: `SECURITY_AUDIT.md` P0 #1–2 and
P1 #3–10. Spot-checks this pass:

- **Authz per route.** All 19 admin routes gate on
  `require_permission("admin.*")` (`backend/admin_routes.py:126`–`571`).
  Crew Hours uses `require_crew_hours_view` / `require_crew_hours_export`
  (`router.py:112`, `:135`); Copilot uses `require_copilot_access`
  (`copilot/router.py:42`); project creation now `_require_project_creator`.
  Uploads/jobs/notifications/modules authenticate only — correct, since each
  filters by `current_user.id`.
- **IDOR: clean.** `download_upload` filters
  `Upload.user_id == current_user.id` (`main.py:380`);
  `/api/downloads/{filename}` resolves through `_owned_output_artifact(db,
  current_user.id, filename)` **before** touching the filesystem (`:713`).
- **CORS: correct.** `resolve_cors_origins` (`config.py:232–260`) trims,
  de-slashes, and makes `*` fatal in production; middleware runs
  `allow_credentials=True` (`main.py`).

### S-1 · Secrets still unrotated
Severity: **BLOCKER (B-4)** · owner-only, **not touched in this pass**
`TECHNICAL_DEBT.md` #3 step 1 reads "in progress". Pending: `JWT_SECRET_KEY`,
`WORKER_HMAC_SECRET`, `SQL_SERVER_USER`/`_PASSWORD`. Until `JWT_SECRET_KEY` is
rotated, anyone with repository history can forge a token for any user.
Two facts that bear on the work:
- Rotating `JWT_SECRET_KEY` forces a one-time logout for everyone. The deploy
  checklist already schedules exactly such a window (step 4, the
  password-stamp change) — ride along rather than spend a second window.
- `WORKER_HMAC_SECRET` is referenced by **no current code path** (grep: only
  `SECURITY_AUDIT.md:50,60` and `TECHNICAL_DEBT.md:30`). It belonged to the
  retired Supabase-era worker. **Revoke** it wherever it is still trusted rather
  than reissuing it.
Owner decision needed? No decision — owner **action**. Nothing else in this
plan should be treated as deployable until this lands.

### S-2 · Whether the deployed `JWT_SECRET_KEY` is a historical value
Severity: **BLOCKER-gating** · `UNVERIFIED`
`SECURITY_AUDIT.md:60` says "old `JWT_SECRET_KEY`"; `TECHNICAL_DEBT.md:32` says
"A live `.env` value was additionally treated as compromised on 2026-08-18".
Whether the value the production host will run is any historical value cannot be
determined from the repository. Owner must confirm before deploy. If it is, B-4
is not merely pending — it is active.

### S-3 · L-7 — the shadow env file `backend/.envpython`
Severity: LOW · unchanged
`backend/.envpython` still exists (133 bytes). `backend/config.py:22` loads
`../.env` and `backend/.env` only — so this file looks live and is not. Git-
ignored; consolidate into `backend/.env`, delete locally, note it in onboarding.

### S-4 · LEON refresh token exposed into an agent context today (NEW)
Severity: **HIGH** · owner-only
`backend/.env` holds `LEON_BASE_URL`, `LEON_REFRESH_TOKEN`,
`LEON_TIMEOUT_SECONDS`, `LEON_MCP_URL`. During this session the **value** on
line 2 (`LEON_REFRESH_TOKEN`) was surfaced into the assistant transcript. The
value was not copied into any file, and is not reproduced here.
`SECURITY_AUDIT.md:52–53` already classes this file as holding a live LEON
credential; the new fact is the exposure event.
Proposed action: rotate the LEON refresh token via LEON, treating the current
value as compromised. Add it to the B-4 rotation batch. Third-party credential —
owner-only, no agent action.
Test: none applicable; confirm the old token is rejected by LEON afterwards.

### S-5 · Residual risks carried forward unchanged
Tokens in localStorage (debt #4); 7-day token lifetime with no refresh rotation;
process-local rate limiting (debt #8); no AV scanning of uploads (`scan_state`
is an honest seam); in-process job execution DoS (debt #1). All already
documented in `SECURITY_AUDIT.md` §"Residual risks".

### S-6 · `pickle.load` in the TCM index cache — latent, **not currently exploitable**
Severity: MEDIUM (latent) · stated precisely to avoid inflation
Evidence: `worker/redsea_toolkit.py:798` `pickle.load(f)` and `:807`
`pickle.dump`, reading/writing `.tcm_index.pkl` inside `self.tcm_folder`
(`cache_path_pkl`, `:787`). Reached from `cmp_tcm` via
`TcmIndexer(str(tcm_dir), threads=4, cache=True)` (`handlers.py:341`).
`app2-migration-plan.md` correctly flags this as arbitrary code execution.
Why it is **not** exploitable today: `tcm_dir = workdir / "in" / "tcm"` is a
fresh per-job directory (`handlers.py:336`), and only `.pdf` files are copied
into it (`pdfs` filter at `:332`, copy at `:339–340`). A file named
`.tcm_index.pkl` can never land there, so `try_load_cache` finds nothing and
`build_index` writes its own cache.
Why it still matters: the guard is an incidental consequence of the copy filter,
not a stated invariant. Any future handler pointing `TcmIndexer` at a persistent
or user-named directory — a shared TCM folder is the obvious next feature —
turns this into RCE with no code change to `redsea_toolkit.py`.
Proposed fix: delete the pickle branch (JSON is already the preferred path at
`:794–796`); or, if the cache must stay binary, gate it behind an explicit
trusted-path assertion. Deleting the branch is behavior-preserving for every
current caller.
Owner decision needed? No. Test: `try_load_cache` ignores a `.tcm_index.pkl`
containing a malicious payload.
Blast radius: none today; worker RCE the day a shared TCM folder ships.

---

## 6. Operational readiness

- **Health checks.** `/health/live` (`main.py:144`) and `/health/ready`
  (`:149`) — DB connectivity plus a genuinely useful migration state
  (`current` / `behind` / `unmanaged` / `unavailable`, `:131–142`), computed
  from the script directory without a database round-trip. Missing: LEON
  (**C-3**).
- **Observability.** The weak point. C-1 + C-2 together mean a LEON failure
  reaches the operator as an exception class name and an HTTP status. These two
  are the highest-value non-blocking fixes in this plan.
- **One-time logout.** Already sequenced as step 4 of
  `docs/deploy-checklist-foundation.md`: `dea3443` binds tokens to the password
  stamp, so every pre-deploy token dies on its first request. Announce before
  the window. Fold the `JWT_SECRET_KEY` rotation (S-1) into the same window.
- **Deploy checklist.** `docs/deploy-checklist-foundation.md` is sound —
  backup-first, dedupe audit, staging rehearsal with a real downgrade, CORS,
  post-deploy verification. Two amendments required: **D-1** (step 2 must dump
  full conflicting rows, not counts) and **D-4** (check the added columns don't
  already exist). Like the onboarding doc, it lives only on
  `docs/dev-onboarding-and-deploy`.
- **Rollback.** Migration `c9d0e1f2a3b4` has a real `downgrade()` (`:70–76`),
  test-gated at `test_revision_defines_an_explicit_real_downgrade`. But
  downgrade **cannot restore the rows the dedupe deleted** — which is precisely
  why the step-1 backup is non-negotiable and why D-1 is a BLOCKER.

### O-4 · The documented verification command cannot run
Severity: MEDIUM
`pytest` is absent from `backend/requirements.txt`, from
`backend/venv`, and from the `codex/backend-dependency-manifest` version of the
manifest. `docs/onboarding-local-setup.md`'s "Verify your setup" step
(`python -m pytest backend/tests/ -q`) therefore fails for a new developer who
followed the doc exactly. Today it works only from a system interpreter that
happens to have pytest.
Proposed fix: add `pytest` (and whatever else the suite imports) to a
`requirements-dev.txt`, referenced by the onboarding doc. Natural companion to
PR #4, whose whole subject is the dependency manifest.
Test: a clean venv from the manifest can run the suite.

---

## 7. PR state and merge order

`gh` is **not authenticated** in this environment (`gh pr list` → "run
gh auth login"), so PR *numbers* below are taken from the task brief and
`TECHNICAL_DEBT.md` #3 / `deploy-checklist-foundation.md` and are labeled
`UNVERIFIED`. The **ordering** is derived from git and is verified.

Verified: `main` is behind every branch by 0 commits, and
`codex/backend-dependency-manifest` (= PR #4, per the deploy checklist's title)
**is an ancestor of all five other branches**. It is the shared trunk, 57
commits ahead of `main`. The other five are independent siblings off it:

| Branch | Commits past the trunk | Tip |
|---|---|---|
| `codex/backend-dependency-manifest` — the trunk | 0 (57 past `main`) | `30490c5` |
| `chore/repo-hygiene` | 1 | `d68dd0d` |
| `docs/dev-onboarding-and-deploy` | 1 | `8779f12` |
| `fix/projects-list-pagination` | 1 | `f1a41a5` |
| `docs/bug-report-2026-08-17` | 9 | `05ba2d7` |
| `fix/crew-hours-heavy-airport-rules` (current) | 15 | `0e2d405` |

Ancestry matrix: no sibling is an ancestor of any other. So after the trunk
merges, the rest can go in any order — **except** for PR-2 below.

### PR-1 · Merging the trunk first lands the 19.8 MB Supabase zip on `main`
Severity: MEDIUM
`accessforge-cloud-main.zip` is tracked on `codex/backend-dependency-manifest`
(`git ls-tree` → present) and untracked only by `chore/repo-hygiene`'s single
commit `d68dd0d`. Merging PR #4 first therefore puts a 19.8 MB archive
containing a Supabase `.env` back into `main`'s working tree until
`chore/repo-hygiene` merges. (The blob is already in history, so this is
hygiene, not new exposure — consistent with debt #3.)
Proposed fix: cherry-pick `d68dd0d` into PR #4, or merge `chore/repo-hygiene`
immediately after with nothing in between.

### PR-2 · `docs/bug-report-2026-08-17` is not a docs-only branch
Severity: **HIGH** — this is the ordering trap
Despite the name, it changes **23 files that `fix/crew-hours-heavy-airport-rules`
also changes**, including 12 backend crew-hours sources (`local_answers.py`,
`augmented.py`, `cabin_heavy.py`, `crew_context.py`, `heavy.py`, `positions.py`,
`schemas.py`, `service.py`, `unknown_resolver.py`, `tools/id_probe.py`), 7 test
files, `types.ts`, `messages.ts`, `CrewDetailFlightRow.tsx`, `i18n/index.tsx`,
and the ADR. Its tip commit (`05ba2d7`, 2026-08-18, "record L-5 exposure
conclusion and M-7 resolution") **documents fixes whose code lives on
`fix/crew-hours-heavy-airport-rules`**.
Merging these two independently will conflict across the crew-hours module.
Proposed fix: decide which branch owns the crew-hours source changes, rebase the
other onto it, and merge the code branch first so the doc branch reduces to
documentation. Needs an owner call (**Q-4**).
Also visible here: **two `MCP_Memory` trees** — the bug-report branch edits
`accessforge-cloud-main/accessforge-cloud-main/MCP_Memory/development/decision-log.md`
while the crew-hours branch edits root `MCP_Memory/development/decision-log.md`.
That is the "MCP_Memory tree merge" debt, now with a concrete collision.

### PR-3 · `docs/dev-onboarding-and-deploy` blocks the teammate
Severity: HIGH (people-blocking, not technical)
Carries `docs/onboarding-local-setup.md`, `backend/tools/seed_dev_data.py`,
`backend/tests/test_seed_dev_data.py`, `docs/deploy-checklist-foundation.md`.
Only 1 commit past the trunk, no overlap with the crew-hours branches. It can
merge as soon as the trunk lands. It is also where D-6's two doc gaps and O-4
should be fixed.

### Recommended merge order
1. **PR #4** `codex/backend-dependency-manifest` (the trunk — everything else
   descends from it), with `d68dd0d` cherry-picked, plus O-4's dev manifest.
2. **`chore/repo-hygiene`** immediately after (PR-1).
3. **`docs/dev-onboarding-and-deploy`** — unblocks the teammate (PR-3).
4. **`fix/projects-list-pagination`** — independent, 1 commit.
5. **Crew-hours pair** in the order the owner rules in **Q-4**.

`TECHNICAL_DEBT.md` #3 step 2 ("close PR #5 and PR #6 before the history
rewrite") sits **after** all of the above: the rewrite must not run while any
of these are open.

---

## 8. Owner decisions needed

Nothing below was decided in this pass. Options are laid out; none is picked.

| ID | Question | Options | Blocks |
|---|---|---|---|
| **Q-1** | `CHECK_RELATIONS` A7/A9/A11 omit themselves (`redsea_toolkit.py:121–140`). Intentional (no unique tasks) or a typo? | (a) intentional — document and add a test asserting the asymmetry; (b) typo — add self-inclusion, changing generated card sets | P-1; gates the B-3 fix |
| **Q-2** | When `module_access` duplicates conflict, which row wins? | (a) most restrictive (`enabled = 0`) — fail safe; (b) newest `created_at` — last-writer-wins; (c) abort the migration and demand manual resolution | **B-1** |
| **Q-3** | `handlers.py:284` claims Check Control "mirrors" `_load_check_csv`, which is an App2 stub. Where did the web rule come from? | (a) it was invented — remove the false comment and mark the rule `discovery_required`; (b) there is an unrecorded source — record it | Check Control parity claim |
| **Q-4** | Which branch owns the crew-hours source changes shared by `docs/bug-report-2026-08-17` and `fix/crew-hours-heavy-airport-rules`? | (a) code branch first, rebase docs onto it; (b) the reverse | **PR-2** |
| **Q-5** | Cover Merge has no App2 implementation (`covers_dir` never set). Dropped feature or unbuilt? | (a) unbuilt — write a spec, keep `under_development`; (b) dropped — remove the module and its handler | Cover Merge parity |
| **Q-6** | LEON health: separate `/health/leon`, or a `leon` block inside `/health/ready`? | (a) separate endpoint — `ready` stays fast and dependency-free; (b) block in `ready` behind a flag — one probe for monitoring | C-3 |
| **Q-7** | Report cache TTL, and is a stale report acceptable to an operator? | (a) 60 s — safe, modest relief; (b) 5 min — real relief, visible staleness; (c) no cache, per-user cooldown only | C-4 |
| **Q-8** | Do `cmp_tcm` / `task_stamping` / `mail_merge` ship at all before parity is evidenced? | (a) keep them reachable and accept unverified output; (b) make `readiness` actually gate job submission so `under_validation` means something; (c) hide them until parity tests pass | B-2/B-3 severity |

Q-8 deserves emphasis: today `readiness` is decorative
(`backend/main.py:827` is its only consumer). Option (b) is a small change that
would convert several of this plan's BLOCKERs into HIGHs by making the app's own
honesty enforceable.

---

## 9. Execution order

Dependencies are stated; everything else is independent.

**Phase 0 — owner only, no agent action.** Blocks the deploy, not the work.
- **S-1 / B-4** rotate `JWT_SECRET_KEY`, `WORKER_HMAC_SECRET`, SQL Server
  credentials; **revoke** `WORKER_HMAC_SECRET` rather than reissue.
- **S-4** rotate the LEON refresh token.
- **S-2** confirm the production `JWT_SECRET_KEY` is not a historical value.
- Answer **Q-1, Q-2, Q-3, Q-4** — these four gate Phase 1.

**Phase 1 — BLOCKERs.** Order matters only where noted.
1. **D-1 / B-1** — corrected step-2 audit query + semantic tie-break per Q-2 +
   the migration test that does not exist yet. *Needs Q-2.*
2. **D-4** — column-existence pre-check in the checklist. Independent; do it in
   the same pass as D-1, same file.
3. **B-2** — replace the substring check match with an exact normalized match.
   Independent of B-3, and it is the smaller, safer fix; land it first.
4. **B-3** — introduce `expand_check` into `cmp_tcm`. *Needs Q-1* — fixing B-3
   without the A7/A9/A11 ruling ships a silent card omission.

**Phase 2 — observability (highest value per line of change).**
5. **C-1** (M-3 non-2xx body) then **C-2** (M-4 `str(exc)`). Do them together:
   either alone leaves LEON failures undiagnosable.
6. **C-3** (M-6 LEON health). *Needs Q-6.*
7. **C-4** (M-5 cache + cooldown). *Needs Q-7.*

**Phase 3 — parity evidence.** All independent of each other. Per the skill's
parity rule: **write down the legacy behavior with evidence, get it confirmed,
then implement.** `app2-module-inventory.md` §2 already holds the verbatim
constants — use it, do not re-read `app2.py` from scratch.
8. `cmp_tcm` gaps 3–5 (marker row, sheet selection, subtask rule).
9. `mail_merge` against `placeholder_index` (§2.3) + alias fan-out + LTR wrap.
10. `task_stamping` against §2.9/§2.11 (Boeing card regex, stamp coordinates).
11. **S-6** delete the pickle branch — behavior-preserving, no ruling needed.
    Can be done any time; do it before any shared-TCM-folder feature.

**Phase 4 — merges.** Section 7's order. PR #4 → `chore/repo-hygiene` →
`docs/dev-onboarding-and-deploy` (fix D-6's two doc gaps and O-4 here) →
`fix/projects-list-pagination` → the crew-hours pair per Q-4.

**Phase 5 — cleanups, all independent.**
12. Supabase deletion pass — §4 groups (a) and (b). Group (b)'s ADRs get
    superseding notes, not deletion. **Requires an approved deletion list.**
13. **C-5** (L-6 `parsing.py`), **C-6** (L-1/L-2/L-3/L-4), **C-7** (I-1 comment).
14. Dead-weight list from the bug report — `cabin_heavy.py` (still present;
    ADR Decision 5 schedules it for deletion next release), the `derive_heavy`
    wrapper (`heavy.py:188`, test-only callers), `positioning_crew`,
    `journeyLog`, `_flight_nid_as_int`, `minimum_required_*`. **Deletion list
    must be approved before anything is removed.**
15. `TECHNICAL_DEBT.md` #10's suite-duration figure (~4½ min → 22½ min).

**Not in this plan, deliberately:** durable jobs (debt #1), relational job
outputs (#2), localStorage tokens (#4), the `redsea_toolkit.py` unwind (#5),
DB dual-source (#6), effectivity/utilization business rules (#7). Each is its
own slice with a settled or pending design; none is a pre-deploy item.

---

## Appendix — what this pass did not verify

Stated so nothing here reads as more certain than it is.

- **PR numbers** (#4/#5/#6) — `gh` unauthenticated; ordering is git-derived and
  verified, numbering is not.
- **Parity of `task_stamping`, `mail_merge`, `cover_merge` output** — the gaps
  listed are structural (missing constants/rules), established by reading. No
  output was compared against App2 on real input. Phase 3 is that work.
- **`2000FC` in the web check list** (P-2) — the web check-list source was not
  located; labeled `UNVERIFIED`.
- **D-3** enum collation — reasoned from the schema, not observed on a live SQL
  Server instance. It is a query to run, not a defect to fix.
- **No SQL Server instance was contacted.** Every DB finding is from the
  migration source, the models, and the offline-DDL tests. The staging rehearsal
  in the deploy checklist remains the live confirmation.
