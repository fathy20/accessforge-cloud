# LEON live capability matrix (S5B)

Read-only discovery against the live `rsx` operator account, 2026-08-15.
Introspection and read queries only — no mutations were issued during this pass.
Status values: **documented** (confirmed live), **inferred**, **unknown**.

## Endpoints in use by the current code

| Purpose | URL | Auth | Status |
|---|---|---|---|
| GraphQL | `https://rsx.leon.aero/api/graphql/` | `Authorization: Bearer <access token>`, refreshed from `LEON_REFRESH_TOKEN` | documented |
| MCP (JSON-RPC) | `https://rsx.mcpserver.leon.aero/mcp` | same bearer token | documented |
| Token refresh | `POST /access_token/refresh/`, **form-encoded** `refresh_token` | — | documented |

The operator MCP endpoint matches the plan's `https://{oprId}.mcpserver.leon.aero/mcp`
pattern with `oprId = rsx`. Trailing slash on `/api/graphql/` is required: without it
the host returns a 403 HTML page.

## GraphQL discovery targets

| Target | Result | Status |
|---|---|---|
| `CrewMember.experienceList` | Exists. **Takes no arguments** — no date-interval filtering at the field level. Return type did not resolve through introspection. | documented (signature), unknown (return shape) |
| `LoginExperience` | `aircraftType, date, dutyTime, blockTime, picTime, position, landingCount, takeOffCount, nightLanding, nightTakeOff, holding, flightCount, dualFlight, icusFlight, landingMonitoringCount, takeOffMonitoringCount, approachList, approachTypeList, loginExperienceNid` | documented |
| `ftl.dutyList(timeInterval)` | Exists. | documented |
| Other FTL fields | `settings`, `ftlDutyForCrewMembers`, `ftlCalculationsForCrewMember(crewMember, timeInterval)`, `ftlViolationsForCrewMember`, `isCompensationTimeCalculationEnabled` | documented |
| `mcp.reportWizard` | Exists → `McpReportWizard.rwFlightScope` → `flightData(dateFilter, columnList, optionalFilters)` and `flightColumnList` | documented |
| `mcp.lastFlightFromAirport` / `lastFlightToAirport` | Exist, both return `Flight` | documented |
| `mcp.tripHistoryListByFlightNidList` | Exists | documented |
| `mcp.flightList(filter: McpFlightFilter)` | Exists, returns `Flight` | documented |

`ftlCalculationsForCrewMember` is the strongest unexplored candidate for the
Hrs/Work Time source of truth. **Not yet reconciled — do not use it for
production totals before S5C.**

## `McpFlightFilter` — why this matters

`mcp.flightList` filters on fields the root `flightList` does not expose:

```
timeInterval, aircraftNidList, flightType, flightStatus, flightNumber,
tripNumber, icaoType, journeyLogCompletionStatus, adepLocationNid,
adesLocationNid, departureCountry, destinationCountry, requestedByNid,
isCnl, isFerry, aocNidList, crewNidList, tagNidList, limit, offset
```

`flightNumber`, `crewNidList`, `tagNidList`, and `limit`/`offset` are all absent
from the root `flightList` filter the current code uses. Server-side filtering by
flight number and pagination are therefore available on the MCP path only.

`timeInterval.start` / `.end` are **`DateTime!`**, not `String!` — a full ISO
timestamp is required (`2026-08-02T00:00:00Z`), not a bare date.

## Crew data availability

| Source | Returns crew identity | Returns position | Returns function |
|---|---|---|---|
| `mcp.flightList { crewMemberList }` | Field exists but came back **empty** for a flight that demonstrably has crew | no | no |
| Root `flightList { crewList { contact position { name posType } flightTrainingType } }` | yes | yes | no (`workSchedule.function` unverified) |
| MCP Report Wizard `get-report-wizard-flight-scope-report` | `crew_codes`, `crew_names` | `crew_position_names` | **no** — `flightTrainingType` and crew-function columns are rejected by the tool |

Crew position does **not** arrive with `mcp.flightList`; it needs a second call.

## Credential identity class — root cause of the Wingman failure

`loggedUser` returns LEON's only explicit statement of what our credential is:

```json
{"message": "Identity type API key is not allowed, use one of the following
             identity types: user session, user access token, personal API key",
 "path": ["loggedUser"],
 "extensions": {"category": "accessRestriction"}}
```

The configured `LEON_REFRESH_TOKEN` resolves to an **API key** identity. That
splits the schema cleanly:

| Scope | Example | Result |
|---|---|---|
| Operator-level | `wingmanAi.wingmanChat.isAvailable` | works — `true` |
| Operator-level | `flightList`, `mcp.*`, Report Wizard, `ftl.dutyList` | work |
| **User-scoped** | `loggedUser` | refused, with the message above |
| **User-scoped** | `wingmanChat.getAllThreads`, `settings`, `startNewConversation` | refused, but as a *generic* error with only a `path` |

Wingman chat is per-user — threads belong to a logged-in identity — so an API key
cannot use it regardless of query correctness. Only `loggedUser` says so plainly;
the chat resolvers surface a generic message instead, which is why this took so
long to isolate.

**To enable Wingman**, the credential must be reissued as a *personal API key*,
*user access token*, or *user session*. No code change will work around it.

Status: **documented**. Confirmed live, twice, with a control.

## Rate limiting — operational constraint

`POST /api/graphql/` serves a short burst then returns HTTP 500
`{"errors":[{"message":"Internal server error"}]}` to *every* document, including
`query { __typename }`, until it cools down. The MCP host is unaffected and stayed
available throughout. Any live probing must be batched into few large documents
rather than many small ones.

LEON masks most execution errors as that same generic 500 with no `path`,
`locations`, or `extensions`. Validation errors, by contrast, return HTTP 400 with
precise messages — those are trustworthy and worth reading in full.

## Open items for S5C

- `CrewMember.experienceList` return shape and how it is filtered by date.
- Whether `ftlCalculationsForCrewMember` reproduces the Hrs/Work Time report.
- Whether `LoginExperience.dutyTime` and `ftl.dutyList` are additive or overlapping.
- Crew **function** (SFA) source — not found on any path tested.
- Heavy classification: still no LEON field and no multiplier. Unresolved.
