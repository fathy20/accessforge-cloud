# Crew Hours Parity Bug Report and Fix

## Metadata

- Bug ID: CREW-HOURS-PARITY-2026-08-09
- Severity: High reporting correctness
- Environment: Existing AccessForge Crew Hours backend, React module, and XLSX export
- Status: Corrected locally; automated verification complete, reviewer/live smoke pending

## Symptom and Expected Behaviour

- Actual: Every code in `crew_codes` received the whole leg block time, including a
  member whose aligned source position was `PSN`. Server filters changed official
  totals, TRN could be replaced by a local UI flag, cross-month returns were queried
  and counted independently, and dependency construction required LEON configuration
  before authentication or the legacy placeholder route could run.
- Expected: Per-member source positions govern only that member's operating inclusion;
  `PSN` contributes no numeric operating time while the leg remains visible. `PAD` and
  the other previously approved tokens retain their existing inclusion behaviour.
  Authoritative text `TRN` remains exact. Connected duties use the same deterministic
  operating crew set and a non-negative break strictly below four hours, and the whole
  duty belongs to its first leg's date/month. Official totals are independent of detail
  filters. LEON configuration is loaded only when live LEON data is requested.

## Reproduction and Evidence

1. The pre-change requested backend gate produced `70 passed, 3 failed`. All three
   failures originated at `get_crew_hours_leon_client()` eagerly calling
   `load_leon_configuration()` during dependency resolution, affecting unauthenticated,
   unconfigured-report, and authenticated legacy-POST baselines.
2. After adding characterization fixtures and before production changes, the combined
   backend slice produced `70 passed, 19 failed`. The failures directly covered PSN
   contamination, missing connected-duty grouping, exact TRN propagation, filter-total
   invariance, buffered reads, lazy configuration, and TRN export handling.
3. The pre-fix focused frontend slice produced `0 passed, 8 failed`. Missing strict-date
   and local-filter helpers, the manual TRN override, and the unguarded request path were
   the observed failure causes.
4. Sanitized verified-boundary fixtures retain only flight number, JL UTC date/OFF/ON,
   crew codes, supplied positions, and official block time. They contain no MCP envelope,
   raw response, token, credentials, JWT, or `journey_log`.

## Analysis

- Trigger: A flight-scope row containing `PSN`, or a connected out-and-back crossing the
  requested month boundary; server-side `position`/`crew_member` filters; an explicit
  authoritative `TRN`; or route resolution without LEON configuration.
- Broken invariants:
  - Crew arrays must be paired by source index before per-member inclusion is decided.
  - Operating crew-set comparison must be order independent and ignore PSN members.
  - A break must satisfy `0 <= break < 4 hours`; 3:59 connects, while 4:00 and 4:01 do not.
  - Official numeric totals are computed before any visible-detail filter.
  - `TRN` is a text sentinel, not a duration and not zero.
- Root causes:
  - `mcp_report.py` aggregated position-blind `crew_codes`.
  - The selected dates were also the MCP read dates, leaving no boundary context.
  - `service.py` filtered while constructing the only crew map and hard-coded
    `FlightItem.is_trn=False`.
  - React maintained a separate manual TRN truth and sent display filters to the report
    endpoint.
  - The anti-demo-fallback dependency factory performed configuration validation eagerly.
- Blast radius: Crew Hours MCP report totals, monthly attribution, detail/search display,
  authenticated report and legacy routes, and XLSX representation. No database, model,
  migration, authentication implementation, global shell, or other statistics module is
  changed.
- Why it escaped: Existing fixtures pinned accumulated durations and MCP parsing but did
  not provide aligned PSN cases, strict break thresholds, verified month-boundary pairs,
  explicit TRN across all layers, or filter-total invariance.

## Fix

- Strategy:
  - Added a backend-owned domain module that pairs source crew arrays, parses the approved
    `Date ADEP [JL][UTC]`, `BLOFF [JL][UTC]`, and `BLON [JL][UTC]` values into timezone-aware
    UTC datetimes, rolls an earlier ON into the next UTC day, constructs deterministic
    operating crew sets, and attributes connected duties.
  - MCP reads use a bounded two-day buffer on each side. Rows are grouped/attributed and
    then filtered to the requested period before aggregation; `records_count` still reports
    the fetched-row count.
  - Per-code aggregation excludes only slots whose aligned position is exactly `PSN`.
    Source rows and per-member positions remain available in flight details. `PAD`, FDP,
    FDPI, RMP, INSP, and unknown positions retain the prior inclusion contract.
  - Service construction now builds every member and every official numeric group total
    first, then applies `position` and case-insensitive partial `crew_member` filters to
    visible members/rows. A supplied totals-only member is retained even with no flight
    row. Exact `TRN` sets member/flight training state and never enters integer totals.
  - React removed the local TRN override. Search and position now filter the loaded detail
    data locally; aircraft and position-token filters continue to filter only flight rows.
    Backend official totals are always displayed from the response. Strict dates are
    validated arithmetically without JavaScript `Date` conversion, and an invalid or
    reversed range is rejected before fetch.
  - XLSX treats `TRN` as authoritative text, retains `[h]:mm` numeric formatting for valid
    accumulated durations, and continues to serialize only approved response fields.
  - LEON client construction is lazy and never restores fabricated demo data.
- Data repair: None.
- Migration: None.
- Rollback/mitigation: Revert this bounded slice as one change; there is no persisted data
  or schema state to unwind.

## Regression Prevention

- Backend fixtures cover normal operating, PSN-only, mixed operating/PSN, explicit and
  totals-only TRN, values `57:35`, `88:30`, `94:40`, totals above 24 hours, 3:59/4:00/4:01,
  negative overlap, crew change, deterministic order, PSN-excluded crew-set comparison,
  June/July no-double-count, and the two approved live boundary cases.
- API coverage pins auth, lazy unconfigured behaviour, legacy 501, strict dates, exact TRN,
  and search/position official-total invariance.
- Frontend coverage pins partial/full/code/case-insensitive search, clear restoration,
  combined position/aircraft/token filtering, authoritative totals under filtered detail,
  exact date serialization, one request per Load click, invalid-range blocking, and removal
  of the manual TRN control.
- Export coverage pins workbook sheets, `[h]:mm`, exact text TRN, unavailable PSN total,
  formula protection, and absence of `journey_log`, credentials, JWT, secrets, identifiers,
  and raw-payload sentinels.

## Final Automated Verification

- Required backend command: `76 passed, 0 failed, 2 deprecation warnings`.
- Focused domain fixture command: `19 passed, 0 failed`.
- Focused frontend command: `3 test files passed; 8 tests passed, 0 failed`.
- `npx tsc --noEmit`: passed with 0 TypeScript errors.
- `npx vite build`: passed for client, SSR, and Nitro production outputs. Vite emitted
  existing advisory warnings for the tsconfig-paths plugin, plugin timings, and large
  chunks; none was a build failure and package/Vite configuration was outside this slice.
- `git diff --check`: passed with 0 whitespace errors. Git emitted Windows LF/CRLF
  conversion notices for the already-dirty worktree; no files were staged or committed.

## June Reference Fixture Provenance

`backend/tests/crew_hours_parity_fixtures.py` derives only the required values from
`docs/architecture/crew-hours-source-decision.md`, section "June 2026 Reference
Reconciliation", Reference column. The fixture retains `90:20`, `94:40`, `0:00`, and
`TRN`; its numeric grand total is `185:00`, with text `TRN` explicitly excluded. No
production roster, crew-specific June total, or TRN name is hard-coded.

## Verified Boundary Fixtures

- Case A: RSX331 and RSX332 preserve the supplied UTC times, 55-minute gap, identical
  deterministic crew set, and supplied positions. Both select into June; neither selects
  into July.
- Case B: RSX123 and RSX124 preserve the supplied UTC times and 60-minute gap. The first
  leg's ON rolls to 2026-07-01 UTC. Both select into June; neither selects into July.
- These are offline regression fixtures from the approved task evidence. This correction
  did not perform or claim a live LEON verification.

## Known Source Limitation

The live flight-scope source cannot identify a ground-only TRN member who has no flight
row, and no production TRN roster/source was invented. If an authoritative monthly
summary supplies that code/value, the backend, API model, UI data contract, and XLSX
Summary preserve exact text `TRN`; position/name enrichment remains unavailable unless an
authoritative source supplies it.

`LAST 7/11`: **BUSINESS_FIXTURE_REQUIRED**. The observed LAZ/Sherif Laz RSX312
VKO-SSH leg on 2026-07-10/11 is not labelled or otherwise approved as the requested
case, so it is not represented as a claimed LAST 7/11 regression fixture.
