# Crew Hours — Verified Technical Assessment & Execution Handoff

**Date:** 2026-08-05
**Repo:** `E:\work\REDSEA\web\last_V01\accessforge-cloud-main\accessforge-cloud-main`
**Branch:** `codex/backend-dependency-manifest` · **HEAD:** `3d363fa`
**Status:** Assessment complete. No code changed. Awaiting approval before implementation.

> **How to use this file:** This is a handoff document for the next agent/session.
> Everything marked VERIFIED was read directly from the code, git, the `docs/architecture/`
> ADRs, or the customer's real Excel exports. Everything marked ASSUMPTION or OPEN
> QUESTION must not be implemented until confirmed.
>
> **This document supersedes the older prose brief that claimed the blocker was
> "GraphQL-dependent report construction and demo fallback". That statement is STALE —
> see §4.**

---

## 0. Hard rules for whoever implements this

1. **Do not discard the uncommitted working tree.** It contains the real MCP-first
   implementation. See §1.
2. **Do not touch `stash@{0}`** (`wip/task-0.4.5-schema-guard-before-statistics`).
3. **No DB writes, no migrations, no runtime DDL.** Crew Hours is read-only this phase.
   Do not create `backend/redsea.db`. Verify root `redsea.db` SHA-256 is unchanged after
   any test run.
4. **No automated test may contact live LEON.** Fake transports only.
5. **Never print, log, or commit the LEON refresh token.** It lives only in
   `backend/.env` (already gitignored).
6. **Do not calculate aviation durations locally.** Consume `blockTimeJourneyLog` from
   LEON. Summing official per-leg values per crew code is report aggregation and is
   allowed. Deriving duration from OFF/ON timestamps is NOT.
7. **Do not create a separate Crew Hours app.** It stays a module inside AccessForge,
   reusing existing auth, layout, `ApiClient`, and the existing token provider.
8. Do not start broad cleanup or refactors outside the scope in §7.

---

## 1. Repository state (VERIFIED)

```
branch : codex/backend-dependency-manifest
HEAD   : 3d363fa993a5d08f0b17dbaea5c66eeb380188e7  ("fix: stabilize crew hours end-to-end demo")
stash  : stash@{0}  wip/task-0.4.5-schema-guard-before-statistics   <-- PROTECTED, untouched
```

Uncommitted files, classified:

| File | Verdict |
|---|---|
| `backend/statistics/crew_hours/mcp_report.py` | **KEEP** — SSE/JSON-RPC parser + `OfficialMcpReport` (totals mapping + validated rows) |
| `backend/statistics/crew_hours/service.py` | **KEEP** — rewritten, now fully MCP-first |
| `backend/statistics/crew_hours/router.py` | **KEEP** — typed error mapping + 422 for unsupported position filter |
| `backend/tests/test_crew_hours_mcp_report.py` | **KEEP** |
| `backend/tests/test_crew_hours_report_api.py` | **KEEP** |
| `backend/__pycache__/auth.cpython-311.pyc` | **REMOVE from git index**, add `__pycache__/` to `.gitignore`. Build artifact, not work. |

Database safety: no `backend/redsea.db` present. No DDL or migration in the crew_hours
code path. VERIFIED.

---

## 2. Actual runtime architecture (VERIFIED from code, not from the brief)

```
src/routes/_authenticated/modules/crew-hours.tsx
  └─ ApiClient.fetch("/statistics/crew-hours/report?from&to&position&crew_member")
      └─ backend/statistics/router.py           prefix /api/statistics
          └─ crew_hours/router.py               GET /crew-hours/report
              └─ service.LiveCrewHoursService.get_crew_hours_report()
                  └─ leon_client.LiveCrewHoursLeonClient.fetch_official_totals()
                      └─ mcp_report.fetch_official_report()
                            token_provider.get_access_token()      (cached, locked)
                            POST initialize        -> Mcp-Session-Id
                            POST tools/call        -> get-report-wizard-flight-scope-report
                            _parse_rpc_body()      JSON | SSE | multi-event | JSON-RPC
                            _extract_report_rows() structuredContent | content[].text
                            _aggregate_report_rows() -> {crew_code: "HH:MM"}
                      └─ OfficialMcpReport(totals, rows)
                  └─ _build_mcp_report_response(report)   <-- rows are the ONLY source
                                                              of crew members AND flights
```

**Key finding: GraphQL is NOT called anywhere in this path.** `flight_query.py`,
`graphql.py`, and `LiveCrewHoursLeonClient.fetch_flights()` are dead code with respect to
the report endpoint.

**Demo fallback is already closed.** `MockCrewHoursLeonClient.fetch_official_totals()`
returns `{}`; `service.py` sees a falsy non-`OfficialMcpReport` and raises
`LeonConfigurationError` → HTTP 503. Fake crew never reaches an HTTP 200 response.

---

## 3. What already works (VERIFIED)

- **Auth / token provider** — caching, expiry, locking, plain-text token support, typed
  errors. Reused correctly. Do not write a second auth implementation.
- **MCP transport** — `initialize` → `Mcp-Session-Id` → `tools/call`, correct
  `Accept: application/json, text/event-stream`, `MCP-Protocol-Version: 2025-03-26`,
  single 401/403 retry with token invalidation.
- **Parser** — plain JSON, SSE, multiple SSE events, JSON-RPC envelope, `result.content`,
  `content[].type == "text"`, one controlled nested JSON-string layer, `structuredContent`,
  safe rejection of malformed payloads.
- **Aggregation** — integer minutes internally, duplicate crew-code removal *within one
  row*, `HH:MM` formatting with no 24-hour ceiling.
- **Identity** — crew code, not name.
- **Frontend** — date/position/crew filters, Load Report, summary cards, expandable crew
  cards, flight table, loading/error/empty states, official-source badge, local TRN toggle,
  correct use of internal `ApiClient` (no browser→LEON calls).

---

## 4. ROOT CAUSE (VERIFIED) — it is NOT GraphQL

The earlier brief's §9 ("service still uses GraphQL flightList; demo fallback returns 2
fake crew") no longer describes the code. That was fixed in the uncommitted work.

### 4.1 Primary blocker: the requested column set is too narrow

`backend/statistics/crew_hours/mcp_report.py:20`

```python
MCP_REPORT_COLUMNS = ("crew_codes", "crew_names", "blockTimeJourneyLog", "blockTimePlan")
```

Four columns. Direct consequences:

1. **Flight detail rows come back empty.** `service._mcp_flight_item()` probes for
   `flight_number`, `adep`, `ades`, `OFF`, `ON`, `aircraft_reg`, `aircraft_type` — none of
   which are requested from LEON. All resolve to `None`; `start_time_utc` / `end_time_utc`
   become `""`.
2. **The position filter always returns 422.** `service._position_values()` finds no
   position field, so any `position != "All"` raises
   `LeonContractError("...does not provide position data...")` → 422. Cockpit / Cabin —
   a core requirement — is non-functional.
3. **There is no date column**, so the month-boundary attribution rule (§6) is
   technically impossible with the current request.
4. **`records_count` is computed but never exposed.** `OfficialMcpReport.records_count`
   exists; `CrewHoursReportResponse` has no field for it.

`docs/architecture/leon-capability-matrix.md` records that
`get-report-wizard-flight-scope-columns-list` returned **1,181 column definitions**. The
data exists. We are simply not asking for it.

### 4.2 Second defect: the frontend fabricates data (fix first, it is a correctness bug)

`src/routes/_authenticated/modules/crew-hours.tsx`, inside the flight detail table:

```tsx
{flight.departure_airport || "CAI"}
{flight.arrival_airport   || "MED"}
{flight.aircraft_reg      || "SU-RSX"} ({flight.aircraft_type || "B738"})
{flight.position          || "CPT"}
```

Because every one of those fields is currently `null` (§4.1), the page renders
**CAI → MED / SU-RSX / B738 / CPT for every flight**, underneath a badge reading
"Official LEON MCP". This is worse than the demo fallback the brief warned about: it is
invented data presented as authoritative. Replace all of these with `—`.

### 4.3 Third defect: wrong report scope

The customer's real LEON export `Hrs Report (34).xlsx` (sheet `crew_flights`) has these
exact headers — VERIFIED by reading the file:

```
Position type | Name | Surname | Date ADEP [JL][UTC] | Aircraft type | Aircraft |
Flight number | ADEP preferred code [JL] | ADES preferred code [JL] | OFF | ON | Block time [JL]
```

`Position type`, `Name`, `Surname` are **scalar per-row** columns. That means LEON's Report
Wizard emits **one row per crew member per leg** when those columns are selected
(~3.8k rows for June 2026), not one row per flight.

Our code requests `crew_codes` / `crew_names` as **arrays**, which yields one row per
flight (552 rows for June 2026 — matches the ADR).

**Conclusion:** the customer already has a LEON export in exactly the shape we need. Align
`columnList` with that export and the whole `crew_codes` array pairing / index-matching
logic in `service.py` becomes unnecessary — and position, date, and per-leg detail all
arrive for free.

---

## 5. MCP field inventory

| Field | Status |
|---|---|
| `crew_codes` (array of str) | **CONFIRMED live** — identity source |
| `crew_names` (array of str) | **CONFIRMED live** |
| `blockTimeJourneyLog` (`"HH:MM"`) | **CONFIRMED live** — the official duration |
| `blockTimePlan` | Requested, never read |
| `block_time_journey_log_decimal` | Mentioned in the ADR; **not requested, not handled** |
| `scope_row_unique_id`, `flightNumber`, `adep`, `ades`, `OFF`, `ON` | **TEST-FIXTURE ONLY.** Not requested from LEON, never observed live. **The names are guesses.** |
| Position type, Date ADEP [JL][UTC], Aircraft, Aircraft type | **CONFIRMED to exist** (customer's Excel export) but **not requested by our API** |

### Unsafe assumptions currently in the code

- `mcp_report._parse_block_time()` accepts only `r"\d{1,3}:\d{2}"`. If LEON returns a
  decimal (the Excel serialises as `0.2256…`), `H:MM:SS`, or `>999h`, it raises
  `LeonContractError` → 502. No fallback to `blockTimePlan` or the decimal column.
- The detail-field key names in `service._mcp_flight_item()` are invented. They must be
  replaced with real column ids from `get-report-wizard-flight-scope-columns-list`.
- `service._split_display_name()` takes the last whitespace token as surname. Wrong for
  names like "Bahaa Eldin Ibrahim", and when `crew_names` is absent it silently uses the
  crew code as the first name.

---

## 6. Month-boundary attribution rule (customer requirement)

### What the customer asked for (translated)

- A pilot flying back past 00:00 into a new month should be counted in the **old** month;
  the new month gets nothing for that leg.
- An out-and-back rotation that spills into the new month stays in the old month.
- **But** if there is a large gap (e.g. a full day), it is a new rotation and counts in the
  new month.
- Chaining must be **per person** — same crew member only, never across different crew.

### VERIFIED finding that simplifies this dramatically

From `6-Jun 26 Hrs.xlsx`, crew member "Sherif Laz", June 2026:

```
2026-06-07  RSX337  SSH→VKO  22:15 → 04:10    lands 06-08, reported under 06-07
2026-06-30  RSX332  SVX→SSH  23:55 → 05:40    lands 07-01, reported under June
Sheet total = 75:05   (arithmetically re-verified: the 14 legs sum to exactly 75:05)
```

The date column is **`Date ADEP [JL][UTC]` — the departure date.** So most of the rule is
satisfied *automatically* by using that column: a leg departing 06-30 and landing 07-01
already belongs to June. **No custom logic needed for the cross-midnight case.**

### The only case that needs code

A return leg that genuinely **departs on 07-01** but belongs to a rotation that started in
June.

**Rotation chaining algorithm:**

1. Order a single crew member's legs chronologically. **Same normalised crew code only.**
2. Chain a leg to the previous one when
   `OFF(current) - ON(previous) < GAP_THRESHOLD`.
3. Attribute the entire rotation to the month of its **first** leg.
4. A gap `>= GAP_THRESHOLD` starts a new rotation → new month.

**Technical requirement:** to evaluate this correctly the MCP query must fetch a **buffer**
window — e.g. the last 2 days of the previous month and the first 2 days of the next month
— then filter after chaining. **The displayed window is not the queried window.** Build
this into the provider signature from the start.

### Policy guardrails (important)

This is a **REDSEA-local business rule, not an official LEON value.** It changes which
month an official value is attributed to. Therefore:

- Ship it **off by default**, so the API matches LEON 1:1 first.
- Tag every moved leg in the response, e.g. `attributed_from: "2026-07-01"`, so it is
  auditable.
- Distinguish it in `hours_source_status`:
  `official_mcp_report` vs `official_mcp_report_redsea_attribution`.

### Second VERIFIED finding: positioning legs are INCLUDED

The `Not-Active` / `PAD` row (RSX331, 5:45) **is included** in Sherif Laz's 75:05.
Excluding it would give 69:20, which is wrong. **Do not filter out Not-Active / PAD legs
from the total — flag them instead** (`is_positioning: true`).

The "AFTER" sheet layout also carries a 13th column holding `No` / `PAD`, which is this
flag.

---

## 7. Execution plan

### Task 0 — Column discovery. MUST come before any code. BLOCKING.

Write a **temporary read-only script outside the repo** (do not commit it) that calls
`get-report-wizard-flight-scope-columns-list` and resolves the real column ids for:

```
position type · crew name · crew surname · crew code ·
date ADEP [JL][UTC] · aircraft registration · aircraft type · flight number ·
ADEP preferred code [JL] · ADES preferred code [JL] · OFF · ON ·
blockTimeJourneyLog · PAD / positioning flag
```

Record the result in `docs/architecture/leon-report-wizard-columns.md`.
Also record whether selecting the scalar crew columns changes the row cardinality from
552 (per-flight) to ~3.8k (per-crew-per-leg) — see §4.3.

**Without this, every line of code below is guesswork about column names.**

### Task 1..N — file-by-file

| File | Responsibility / Change | Tests | Risk |
|---|---|---|---|
| `mcp_report.py` | Expand `MCP_REPORT_COLUMNS` with discovered ids. Split `REQUIRED_COLUMNS` vs `OPTIONAL_COLUMNS`. Introduce an explicit `McpReportRow` normaliser instead of `_first_string()` guessing. Widen `_parse_block_time()` to accept `H:MM`, `HH:MM:SS`, decimal, and `>999h`. | new-shape parser fixtures; duration variants; missing-required-column → contract error | **MED** — a LEON column-id change becomes a 502. Error message must name the missing column. |
| `service.py` | If rows are crew-expanded, key on the row's own crew code and **delete the array-pairing / index-matching logic entirely**. Read position from the real row → **remove the 422 path**. | grouping by code; intra-row dedup; position filter; crew filter | LOW |
| `schemas.py` | `FlightItem`: add `flight_date`, `block_time`, `is_positioning`; make `start_time_utc` / `end_time_utc` `Optional`. `CrewHoursReportResponse`: add `records_count`, `grand_total`, `capabilities: {position_filter: bool, flight_details: bool}`. | schema snapshot | LOW |
| `router.py` | Align mapping with the agreed contract: `LeonTransportError` → **503** (currently 502), `LeonConfigurationError` → 503, `LeonTimeoutError` → 504. **`LeonTimeoutError` subclasses `LeonTransportError`, so it must be caught first** — it currently is; keep it that way. Add `from <= to` validation → 422. | one test per status code | LOW |
| `crew-hours.tsx` | **Delete every hardcoded fallback** (`\|\| "CAI"`, `"MED"`, `"SU-RSX"`, `"B738"`, `"CPT"`) → render `—`. Add Date and Block time columns. Disable the position dropdown when `capabilities.position_filter === false`. Guard `crew.name[0]` against empty strings. | `npx tsc --noEmit`, `npx vite build` | LOW — highest correctness priority |
| `leon_client.py` | Mark `fetch_flights` and `MockCrewHoursLeonClient.fetch_flights` as deferred / dev-only and move them out of the protocol used by the report path. | — | LOW |
| `transport.py` | **Do not change.** The proxy failure is environmental. Clean `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` in the local launch script. Do not hardcode `trust_env=False`; do not add `LEON_TRUST_ENV` unless production requires it. | — | — |

Out of scope this phase: Excel export, PDF/print, TRN persistence, manual adjustment,
variance workflow, Crew Days, GraphQL enrichment.

---

## 8. Proposed API contract

```json
{
  "period": { "from": "2026-06-01", "to": "2026-06-30" },
  "source": "leon_mcp_report",
  "hours_source_status": "official_mcp_report",
  "records_count": 3864,
  "total_crew": 169,
  "total_flights": 552,
  "grand_total": "12480:35",
  "capabilities": { "position_filter": true, "flight_details": true },
  "crew_members": [
    {
      "crew_id": "AKA",
      "person_code": "AKA",
      "name": "Ahmed",
      "surname": "Kamel",
      "position_type": "Cockpit",
      "status": "normal",
      "official_total": "95:45",
      "raw_official_total": "95:45",
      "reference_total": null,
      "variance_minutes": null,
      "flight_count": 18,
      "flights": [
        {
          "flight_nid": "…",
          "flight_date": "2026-06-05",
          "flight_number": "RSX311",
          "departure_airport": "SSH",
          "arrival_airport": "VKO",
          "start_time_utc": "15:35",
          "end_time_utc": "21:25",
          "aircraft_reg": "SURSB",
          "aircraft_type": "737-800",
          "block_time": "5:50",
          "position": "Cockpit",
          "is_positioning": false,
          "is_trn": false
        }
      ]
    }
  ]
}
```

Durations are integer minutes internally, formatted `H:MM` at the boundary with no
24-hour ceiling (`0:00`, `5:50`, `95:45`, `3452:25` are all valid).
`reference_total` and `variance_minutes` stay `null` this phase.

---

## 9. Frontend contract

- **Official totals** — `official_total` under an "Official LEON MCP" badge, only when
  `hours_source_status === "official_mcp_report"`.
- **Missing names** — show the crew code alone. Never invent a name. Never index into an
  empty string for initials.
- **Missing detail fields** — `—`. **No hardcoded placeholders.**
- **Loading** — existing skeleton with `aria-busy` / `aria-live`.
- **Error** — existing destructive alert with Retry. Show the API `detail`, never a raw
  LEON payload or stack trace.
- **Empty** — HTTP 200 with `crew_members: []` renders the existing empty card.
- **Position capability** — when `capabilities.position_filter === false`, disable the
  dropdown with a tooltip explaining the LEON limitation. Do not send an unsupported
  filter and do not fake a classification.
- **TRN** — stays a local, non-persisted UI toggle. It must never mutate
  `official_total`.

---

## 10. Error behaviour

| Status | Condition |
|---|---|
| **200** | MCP succeeded. Always real rows. `crew_members: []` is a valid 200. |
| **422** | Invalid date format, `from > to`, or a position filter the report cannot support. |
| **502** | `LeonResponseError`, `LeonContractError` (missing required column, malformed duration), auth failure. |
| **503** | `LeonConfigurationError` (LEON not configured) or `LeonTransportError`. |
| **504** | `LeonTimeoutError`. |

Demo data must never appear in a 200. Never expose tokens, `Authorization` headers, raw
LEON payloads, or stack traces.

---

## 11. Test plan

- **Parser** — new column shape; duration variants (`H:MM`, `HH:MM:SS`, decimal, `>999h`);
  missing required column; SSE multi-event; JSON-in-string; malformed payload rejection.
- **Service** — grouping by normalised crew code; intra-row duplicate code dedup; position
  filter; crew filter; (later) rotation attribution + buffer window.
- **API** — 200 / 422 / 502 / 503 / 504; `records_count` present; no demo data on 200.
- **Frontend** — `npx tsc --noEmit`, `npx vite build`; assert no hardcoded fallback strings
  remain.
- **DB safety** — root `redsea.db` SHA-256 unchanged after the suite; `backend/redsea.db`
  never created.
- **Live smoke** — manual only, after env proxy vars are cleared. Never automated.

---

## 12. Acceptance criteria for this phase

- `GET /api/statistics/crew-hours/report?from=2026-06-01&to=2026-06-30` → 200
- `records_count > 3000` and `total_crew ≈ 169`
- `?position=Cockpit` → **200, not 422**
- Every flight row carries real date, flight number, ADEP, ADES, OFF, ON, block time
- **Zero hardcoded fallback values in `crew-hours.tsx`**
- Crew `AKA` total `= 95:45` (matches `docs/architecture/crew-hours-source-decision.md`)
- Crew "Sherif Laz" total `= 75:05` (matches `6-Jun 26 Hrs.xlsx`) — **strongest available
  end-to-end assertion; use it as the golden test**
- Full backend suite green, `tsc --noEmit` green, `vite build` green,
  `git diff --check` clean
- Root `redsea.db` hash unchanged

---

## 13. OPEN QUESTIONS — do not implement these until answered

1. **`GAP_THRESHOLD` for rotation chaining** — the customer said "a big gap, e.g. a day".
   Literal reading is 24h, but that would attribute a 3-day rotation entirely to its first
   day. Standard aviation reporting practice is a 10–12h rest break.
   **Recommendation: 12 hours, configurable.** Needs Ops confirmation.
2. **PAD / Not-Active legs included in the total** — the Excel says yes (§6). Confirm with
   Ops before locking it in.
3. **TRN source** — LEON field, or a manual list from Ops? Currently UI-local only.
4. **Rotation attribution default** — on or off? Recommendation: **off**, so phase 1 is
   provably 1:1 with LEON.

---

## 14. Risks

| Risk | Mitigation |
|---|---|
| LEON changes a Report Wizard column id | Required-vs-optional column split; contract error naming the column; column list captured in `docs/architecture/leon-report-wizard-columns.md` |
| Crew names absent from the report | Fall back to crew code; never invent a name |
| Position field absent after all | Report `capabilities.position_filter: false`; disable the UI filter; no fake classification |
| Larger crew-expanded payload (~3.8k rows) is slow | Measure in Task 0. If slow, keep the per-flight scope for totals and add the detail scope as a second, separately-failing call. |
| Duplicate records across the buffer window | Deduplicate on the row unique id before aggregation |
| Deltas vs the manual report (e.g. AHU 85:45 vs 90:20 reference) | Documented in the ADR. Surface via `reference_total` / `variance_minutes` in a later phase, not now. |
| Local proxy env breaks live calls | Clear `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` in the launch script; do not hardcode `trust_env` |

---

## 15. Architectural notes beyond this phase (context, not tasks)

**Sector mismatch.** The backend already has a sector layer
(`backend/statistics/`, prefix `/api/statistics`). The frontend is flat
(`src/routes/_authenticated/modules/*`) with a hardcoded nav list in
`src/components/app/AppSidebar.tsx`. Target shape:

```
backend/                              src/routes/_authenticated/
  statistics/                           sectors/
    crew_hours/     <-- exists            statistics/
    crew_days/      <-- phase 2             crew-hours.tsx
    _shared/leon/   <-- see below           crew-days.tsx
  engineering/                            engineering/
  inventory/                              inventory/
```

**The one refactor worth doing early:** lift the token provider, transport, MCP client, and
a Report Wizard column registry out of `crew_hours/` into `statistics/_shared/leon/`.
Crew Days will hit the *same* MCP server and the *same* Report Wizard. If this is not done
before Crew Days lands, the result is either duplicated auth or a wrong dependency from
`crew_days` onto `crew_hours`. Cheapest now, most expensive later.

**`AppSidebar.tsx`** should become a registry driven by a `sector` field so that adding a
module is one entry rather than a UI edit. The existing `moduleKey` gating already
supports this pattern.

**Hrs Report vs Crew Days.** Not an either/or. Hrs Report first: it is ~95% built, its
source is confirmed live (552 records), and it builds the shared foundation (MCP client,
column registry, rotation engine, Excel exporter) that Crew Days then reuses as one more
adapter. Crew Days' source is unconfirmed — `get-duty-list` is `NOT_TESTED` and
`get-crew-ftl-sheet` returns HTTP 500 from LEON. Both share the same four-sheet Excel
shape (`Cockpit | Cockpit Summary | Cabin | Cabin Summary`), so the exporter is written
once with the metric as a parameter.

---

## 16. SECURITY — action required

The LEON API key (a full-scope refresh token for operator 2207) was pasted in plaintext
into a chat prompt and into `v_2/v_2.txt`.

- **Rotate it in LEON now.** Treat the current value as compromised.
- The replacement goes only into `backend/.env` (verified gitignored).
- Do not paste it into prompts, docs, or notes again.
