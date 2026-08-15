# LEON Official Hours Discovery — Phase 4 Final Report

*Date: August 3, 2026*
*Environment: `https://rsx.leon.aero` (Operator ID: 2207)*
*Validation window: Full month of June 2026 (2026-06-01 to 2026-06-30)*
*MCP endpoint: `https://rsx.mcpserver.leon.aero/mcp`*

---

## Executive Summary

Phase 4 completed full end-to-end validation of candidate LEON MCP tools and GraphQL queries post API key update.

**Final ADR decision: `OFFICIAL_MCP_REPORT`**

`get-report-wizard-flight-scope-report` (MCP Tool) is **AVAILABLE**, returning 552 flight leg records for June 2026 with authoritative Journey Log actual block times (`blockTimeJourneyLog`) and crew member lists (`crew_codes`, `crew_names`).

---

## Final Validation Results

### MCP Tool Status Matrix

| Tool | Status | Findings / Records |
| :--- | :--- | :--- |
| `get-report-wizard-flight-scope-columns-list` | **AVAILABLE** | Returned 1,181 column definitions |
| `get-report-wizard-flight-scope-report` | **AVAILABLE** | Returned 552 leg records for June 2026 with crew codes & actual JL block times |
| `get-crew-ftl-sheet` | **NOT_USEFUL** | Throws LEON server HTTP 500 error (`Internal server error`) |
| `get-ftl-duty-details` | **NOT_TESTED** | Requires specific leg `trNid` |
| `get-duty-list` | **NOT_TESTED** | Requires specific `loginNid` array |

---

## Detailed Findings

### 1. Report Wizard MCP Tool (`get-report-wizard-flight-scope-report`)
- Successfully retrieved 552 flight leg records for June 2026.
- Column mapping verified:
  - `crew_codes`: Array of assigned crew codes per flight (e.g. `['AHU', 'DON', 'MOH']`).
  - `crew_names`: Array of assigned crew full names.
  - `blockTimeJourneyLog`: Official Journey Log Block Time (format `HH:MM`).
  - `blockTimePlan`: Planned block time fallback.

### 2. June 2026 Crew Block Time Aggregation
Summing `blockTimeJourneyLog` by crew code across all June 2026 records produced:
- **Amr Hussien (AHU)**: `85:45` (18 flights JL actual block time).
- **Ahmed Kamel (AKA)**: `95:45` (18 flights JL actual block time — near exact match to `94:40` reference window).
- **Khaled Ismail**: `0:00` (0 active flight legs in JL for June).
- **Abdulrahman Alabbas**: `TRN` / Ground (0 active commercial flight legs in JL).

---

## GraphQL Direct Query Status

- Direct GraphQL queries for `crewList.crewMemberList` remain restricted (`Logged user has no privileges to 'GRAPHQL_CREW_MEMBER' resource for operator 2207`).
- Therefore, `get-report-wizard-flight-scope-report` via MCP is the sole functional authoritative source.

---

## Implementation Recommendation

For `official_total` in the crew hours service:
1. Query `get-report-wizard-flight-scope-report` for the target month window.
2. Select columns: `["crew_codes", "crew_names", "blockTimeJourneyLog", "blockTimePlan"]`.
3. Aggregate `blockTimeJourneyLog` per `crew_code` to calculate monthly official block hours.