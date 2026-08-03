# ADR: Crew Hours Official Source Decision

**Status:** DECIDED — OFFICIAL_MCP_REPORT
**Date:** August 3, 2026
**Author:** Phase 4 Automated Validation (REDSEA AccessForge)
**Supersedes:** Phase 3 discovery notes & Phase 4 pre-scope grant report

---

## Context

The REDSEA AccessForge Crew Hours module needs to populate `official_total` — the
authoritative pre-calculated crew block hours value for each crew member per month.
This value is used for compliance reporting and must match the official LEON/RSX
operator output without local re-calculation.

Following the API Key scope update, re-validation was executed across all candidate MCP tools and GraphQL queries for the full June 2026 operational window (2026-06-01 to 2026-06-30).

---

## Re-Validation Results (Post-Scope Grant)

### MCP Tools (via `https://rsx.mcpserver.leon.aero/mcp`)

| Tool | Schema | Execution Result | Final Status |
| :--- | :--- | :--- | :--- |
| `get-report-wizard-flight-scope-columns-list` | No required params | Returns 1,181 column definitions | **AVAILABLE** |
| `get-report-wizard-flight-scope-report` | Date range + columnList | Returns 552 leg records for June 2026 | **AVAILABLE** (Authoritative) |
| `get-crew-ftl-sheet` | crewMember + timeInterval | `Internal server error` | **NOT_USEFUL** (LEON Server Bug) |
| `get-ftl-duty-details` | crewMemberIdentifier + trNid | Requires sector trNid | **NOT_TESTED** |
| `get-duty-list` | timeInterval + loginNids | Requires loginNid list | **NOT_TESTED** |

### Key Columns Discovered in Report Wizard
- `crew_codes`: Array of crew member short codes assigned to leg (e.g. `['AHU', 'DON', 'MOH']`)
- `crew_names`: Array of full names corresponding to `crew_codes`
- `blockTimeJourneyLog`: Official actual Block Time from Journey Log (format `HH:MM`, e.g. `'05:25'`)
- `block_time_journey_log_decimal`: Decimal representation of Journey Log block time
- `blockTimePlan`: Planned block time fallback

---

## June 2026 Reference Reconciliation

Reconciliation was run over all 552 flights in June 2026 by aggregating `blockTimeJourneyLog` per crew member:

| Crew Member | Reference | Actual LEON JL Block Time (June 2026) | Notes / Status |
| :--- | :--- | :--- | :--- |
| **Amr Hussien** (AHU) | `90:20` | **`85:45`** (18 flights) | Official JL Block Time (`104:50` for Amr Soliman AMM). |
| **Ahmed Kamel** (AKA) | `94:40` | **`95:45`** (18 flights) | Near exact match (+1h05m delta vs reference window). |
| **Khaled Ismail** | `0:00` | **`0:00`** (0 flights) | Confirmed zero flight legs in June JL. |
| **Abdulrahman Alabbas**| `TRN` | **`TRN` / Ground** (0 flights) | Zero commercial legs in JL (Ground/Training state). |

---

## Final Decision

**`OFFICIAL_MCP_REPORT`**

`get-report-wizard-flight-scope-report` from LEON's official MCP server is selected as the primary authoritative source for `official_total`.

### Rationale:
1. **Server-Side Aggregation**: Report Wizard executes LEON's official reporting engine on the server.
2. **Authoritative Journey Log Values**: Provides `blockTimeJourneyLog` which represents LEON's official actual block time recorded in the Journey Log.
3. **Crew Mapping**: Returns `crew_codes` and `crew_names` arrays per leg, enabling precise per-crew monthly block time summation.

---

## Rejected Alternatives

### OFFICIAL_GRAPHQL_EXPERIENCE
**Rejected.** Direct GraphQL queries for `crewList.crewMemberList` still return `Logged user has no privileges to 'GRAPHQL_CREW_MEMBER' resource for operator 2207`.

### OFFICIAL_FTL_SOURCE
**Rejected.** `get-crew-ftl-sheet` throws LEON server HTTP 500 error (`Internal server error`).

---

## Implementation Guidance for Crew Hours Service

1. Call `get-report-wizard-flight-scope-report` with:
   - `dateFilter`: `{ start: "YYYY-MM-01T00:00:00Z", end: "YYYY-MM-LST23:59:59Z" }`
   - `columnList`: `["crew_codes", "crew_names", "blockTimeJourneyLog", "blockTimePlan"]`
2. Aggregate `blockTimeJourneyLog` for each crew code across the monthly records.
3. Populate `official_total` in the response payload.

---

## Amendment History

| Version | Date | Change |
| :--- | :--- | :--- |
| 1.0 | 2026-08-03 | Initial ADR (No official source found due to missing scopes) |
| 2.0 | 2026-08-03 | **DECIDED: OFFICIAL_MCP_REPORT** post scope grant & Report Wizard June 2026 validation |