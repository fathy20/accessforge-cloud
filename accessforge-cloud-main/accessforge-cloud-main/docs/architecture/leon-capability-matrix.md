# LEON API Capability & Scope Matrix

*Last Updated: August 3, 2026*
*Environment: `https://rsx.leon.aero` (Operator ID: 2207)*
*MCP Server: `https://rsx.mcpserver.leon.aero/mcp` (115 tools, protocol 2025-03-26)*

---

## Phase 4 Re-Validation Results (Post Scope Update)

### MCP Tool Execution Results

| Tool | Status | Execution Finding | Target Metric / Fields |
| :--- | :--- | :--- | :--- |
| `get-report-wizard-flight-scope-columns-list` | **AVAILABLE** | Returned 1,181 column definitions | Metadata definitions |
| `get-report-wizard-flight-scope-report` | **AVAILABLE** | Returned 552 leg records for June 2026 | `crew_codes`, `crew_names`, `blockTimeJourneyLog` |
| `get-crew-ftl-sheet` | **NOT_USEFUL** | Throws LEON server HTTP 500 (`Internal server error`) | FTL sheet metrics |
| `get-ftl-duty-details` | **NOT_TESTED** | Requires specific leg `trNid` | Duty sector details |
| `get-duty-list` | **NOT_TESTED** | Requires specific `loginNid` array | Duty timeline |

---

## Final Official Source Decision

| Field | Source Chosen | Implementation Details |
| :--- | :--- | :--- |
| `official_total` | **`OFFICIAL_MCP_REPORT`** | Uses MCP tool `get-report-wizard-flight-scope-report` with `blockTimeJourneyLog` aggregated per `crew_codes` for target month window |