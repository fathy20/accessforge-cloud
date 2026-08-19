# Unattended Log — 2026-08-19

Plan: `docs/audit/deploy-readiness-plan-2026-08-19.md` (approved).
Window scope, per owner: **B-1 and B-2 only.** Everything else queued below.

Owner ruling in force (Q-2): **most restrictive row wins** in the
`module_access` dedupe — if any duplicate has `enabled=False`, that row is the
survivor. A migration must never grant access someone was explicitly denied.

| # | Item | Status | Commit |
|---|---|---|---|
| 1 | B-1 — `module_access` dedupe by restrictiveness, not `MIN(id)` | DONE | `556037d` |
| 2 | B-2 — `cmp_tcm` exact check match, not substring | DONE | `48d60f0` |

---

## B-1 — what changed

`alembic/versions/c9d0e1f2a3b4_integrity_indexes.py`
- `module_access` dedupe now selects the survivor by restrictiveness tier
  (`CASE WHEN enabled = 0 THEN 0 ELSE 1 END`), with `MIN(id)` demoted to a
  tie-break *inside* the winning tier, so the result stays deterministic.
- `user_roles` dedupe deliberately **unchanged** — its duplicate groups are
  `(id, user_id, role)` and nothing else, so the rows are interchangeable. The
  asymmetry is commented in both places so nobody "unifies" them later.
- **"Restrictive" is defined as `enabled = 0` exactly.** Justification, not
  assumption: `_module_visibility_inputs` (`backend/main.py:840`) denies on
  `ModuleAccess.enabled == False`, which never matches NULL. So NULL groups with
  True as permissive rather than being invented into a third meaning.
- Portability: the tier is a `CASE` expression because **SQL Server rejects
  `MIN()` over a `bit` column**; join predicates are NULL-safe so rows with a
  NULL `user_id`/`module_id` still collapse to one survivor instead of all being
  deleted (the naive correlated rewrite deletes them all).
- Docstring now carries the four **pre-migration audit queries**, including the
  one that surfaces groups *disagreeing* about access. The old
  `COUNT(*)`-only query cannot detect a conflict; this one prints every row.
  Also added the `add_column` pre-flight for `projects.tail_number`/`station`
  (plan item D-4), since the baseline was adopted from an existing SQL Server DB.

`backend/tests/test_alembic_migrations.py`
- Harness extended with an optional `target` revision (additive; every existing
  call site keeps its behaviour).
- `test_module_access_dedupe_keeps_the_denied_row_over_an_enabled_duplicate` —
  the enabled row is given the lexicographically **smaller** id on purpose, so
  the old `MIN(id)` rule keeps the wrong row. **Verified RED before the fix:**
  `AssertionError: True != False : the denied row must survive; kept
  '00000000-aaaa' with enabled=1`.
- `test_module_access_dedupe_is_deterministic_when_no_row_is_denied` — control;
  passed both before and after, proving the fix does not change behaviour where
  there is no conflict of intent.
- `test_module_access_dedupe_collapses_null_keyed_duplicates_without_deleting_them`
  — added after an edge case the first two tests did not cover. Confirmed by
  direct probe across six group shapes (conflict, both-deny, single row, NULL
  `enabled` vs deny, NULL `user_id`, NULL `user_id`+`module_id`): 6 survivors
  from 11 rows, exactly one per group, deny winning every conflict.
- File result after the fix: **25 passed** (22 pre-existing + 3 new), including
  the SQL Server offline-DDL gate, so the new SQL is offline-safe.

## B-2 — what changed

`worker/handlers.py` (`cmp_tcm`)
- Replaced `if check_code in cell_val or cell_val == check_code` with App2's
  **two-tier equality** (`app2.py:3247-3260`): whitespace-stripped upper-cased
  cell vs target, then `_normalize_check_code` of both sides.
- Hoisted the loop-invariant `df_str.shape[1] > 24` check out of the row loop.

`worker/toolkit.py`
- New `normalize_check_code()` that calls `rt.RedseaApp._normalize_check_code`
  **unbound** (it never touches `self`). Deliberately *not* a transcription of
  App2's transformation table — a second copy of that rule is exactly the drift
  pattern that produced the Heavy divergence. `redsea_toolkit.py` stays frozen.

`backend/tests/test_cmp_tcm_parity.py`
- Extended the existing harness (which already runs App2's real
  `_extract_tasks_from_excel_mpd_rsd` and compares against the web handler — the
  right pattern; its fixture simply had no `A10` row).
- `test_a_related_check_code_is_not_matched_by_substring`. **Verified RED before
  the fix:** asked for `A1`, the web handler produced
  `['27-001-00.pdf', '27-002-00.pdf']` while App2 returned only `27-001-00`.
- After the fix: **8 passed** across `test_cmp_tcm_parity`, `test_check_control`,
  `test_api_check_control`.

## Correction made to the approved plan

Parity gap #3 in the plan was **wrong** and has been corrected in place. I wrote
that App2 reads rows only *after* the `CMPISS03 R1` marker. It does not:
`mpd_rsd_start_row` is assigned at `app2.py:3222/3232` and **never read**
(`grep -n mpd_rsd_start_row app2.py` → 3 hits, all writes). The marker is a
**gate** — absent, the extraction returns `[]` at 3238 — not a slice. So the web
app's "scans all rows" is parity-correct; the real difference is that the web app
never checks for the marker at all. Severity unchanged (Phase 3), description
fixed.

---

## QUEUED FOR OWNER

### Stopped on / needs your decision

1. **B-1 dedupe is O(n²) on `module_access`.** The new rule uses a correlated
   subquery, and the non-unique `ix_module_access_user_id` /
   `_module_id` indexes are created **after** the dedupe, so the scan is
   unindexed. Fine at realistic size (per-user overrides — hundreds to low
   thousands of rows); it would bite on a table an order of magnitude larger.
   The cheap fix is to move the non-unique `INDEXES` loop **before** the dedupe
   (creating them on duplicate data is legal; only the UNIQUE ones must come
   after). I did **not** reorder DDL in a production-bound migration on my own
   judgement. Your call.
2. **`docs/deploy-checklist-foundation.md` step 2 still carries the old
   `COUNT(*)` audit query.** That file exists only on
   `docs/dev-onboarding-and-deploy`, which I am not permitted to touch this
   window. The corrected queries live in the migration docstring meanwhile —
   fold them into the checklist when that branch merges.

### Out of scope by instruction (not blocked by a discovery)

- **B-3** (`expand_check` in `cmp_tcm`) — blocked on **Q-1** (A7/A9/A11
  self-exclusion). Note: `expand_check` is already imported at
  `worker/handlers.py:23` and never called, so the change really is one call
  site. Not touched.
- **B-4 / S-1 / S-2** — secrets. Owner only.
- **S-4** — LEON refresh token: owner rotating. Status recorded only; the value
  was never read, copied, or referenced.
- **Q-1, Q-3, Q-4, Q-5, Q-6, Q-7, Q-8** — no ruling yet; not guessed.
- **M-3 / M-4 / M-6 observability, L-6 renames** — in the owner's item 3, then
  descoped by their closing instruction. Ready on a word; M-3 and M-4 need no
  ruling.
- **Merges, deletions, history rewrite, migrations against a real database** —
  forbidden this window. None attempted.

### Correction to the owner's work list

**M-2 and I-2 are already resolved and test-pinned** (verified in PASS 1), so
item 3 reduces to L-6 + M-3/M-4/M-6. No work was done on M-2/I-2.

## Verification

Full backend suite after both fixes: **510 passed in 242.74s (4:02)** — the
507-test baseline plus the 3 new tests, all collected in that run. Frontend
suite unchanged and untouched (48 passed in PASS 1; no `src/` files were edited).

Honesty notes on how that number was reached:
- Both fixes were developed test-first, with the red output captured verbatim
  above before any production line changed.
- **One** full-suite run covers both items rather than one run per item. The
  first full run was started after B-1 but before B-2 landed, so its result
  would have been ambiguous; it was stopped and re-run clean. Per-item targeted
  suites were green individually (25 for B-1's file, 8 for B-2's).
- **A retraction.** The PASS 1 plan claimed the suite takes 22m 29s versus the
  "~4½ minutes" in `TECHNICAL_DEBT.md` #10, and called the debt item's number
  wrong. That was a cold-cache run. Warm, the same suite takes 4m 02s, matching
  the documented figure. The plan has been corrected and #10 needs no change.

## Commits on this branch

`556037d` (B-1) and `48d60f0` (B-2), on `fix/crew-hours-heavy-airport-rules` —
the branch that was already checked out. Only my own files were staged: the
working tree carried 14 pre-existing uncommitted crew-hours changes from before
this window, and those remain untouched and uncommitted.
