# LEON Crew Hours — Discovery and Implementation Plan

## Decision

S5 manual aggregation is paused. No production Crew Hours calculations should be implemented until the LEON source of truth is identified and reconciled against the LEON Hrs/Work Time output.

## Evidence from the supplied LEON API documentation

### 1. Crew Experience exists as a first-class LEON model

The schema changelogs show `CrewMember.experienceList` and the `LoginExperience` type. Across later schema changes, the model includes or evolves fields for:

- `aircraftType`
- `date`
- `blockTime` (`TimeLong`)
- `dutyTime` (`TimeLong`)
- `flightCount`
- `takeOffCount`
- `landingCount`
- `takeOffMonitoringCount`
- `landingMonitoringCount`
- `approachList`
- `approachTypeList`
- `dualFlight`
- `icusFlight`
- `picTime`
- `loginExperienceNid`

This model is a much closer match to the requested Crew Hours module than a generic `flightList` sum.

### 2. LEON supplies a flight/Journey Log evidence query for Crew Experience

The sample query `getFlightsWithCrewMembersAndJLForCrewExperience.txt` returns:

- confirmed non-cancelled flights in a date range
- flight start/end UTC timestamps
- aircraft registration and type
- crew member identity and position
- `flightTrainingType`
- Journey Log takeoff and landing crew
- pilot-monitoring takeoff and landing crew
- landing count
- approaches and approach types
- autoland

This should be treated as raw evidence and a reconciliation source, not automatically as the primary aggregated source.

### 3. Duty is a separate LEON domain

The sample `dutyList` query returns duties by crew login and date interval, including:

- `dutyNid`
- start/end times
- start/end airports
- duty type and definition
- crew login identity

The existence of both `LoginExperience.dutyTime` and `dutyList` means their semantics must be verified before either is used. They must not be added together without proof.

### 4. MCP is present in two layers

The documentation exposes an operator-specific MCP server:

`https://{oprId}.mcpserver.leon.aero/mcp`

using Bearer access-token authentication.

The GraphQL schema changelogs also show `Query.mcp` and MCP-related fields/types, including:

- `reportWizard`
- `fuel`
- `mx`
- `lastFlightFromAirport`
- `lastFlightToAirport`
- `tripHistoryListByFlightNidList`

The presence of `McpReportWizard` is especially relevant: a report path may exist through MCP/GraphQL even though the public sample files do not document a direct `Hrs Report` query.

### 5. No documented Heavy-hours multiplier was found

The supplied repository does not define a rule such as:

`heavy hours = block hours × multiplier`

Aircraft type and MTOW are available in some models, but no documented calculation rule connects them to a Crew Hours multiplier. Heavy should therefore be considered an experience category/classification until LEON or the operator's report proves otherwise.

## Proposed source-of-truth priority

1. LEON Hrs/Work Time report or an MCP/report-wizard tool returning the same result.
2. `CrewMember.experienceList`, if it represents the report values for the requested interval.
3. A hybrid of Crew Experience, Duty/FTL, and flight/Journey Log evidence.
4. Fully local derivation from flights only, as the last option.

## Architecture for the existing backend module

Keep the current secure LEON authentication and GraphQL transport from S4. Do not bind the Crew Hours endpoint directly to `flightList`.

Introduce a provider boundary:

```python
class CrewHoursProvider(Protocol):
    async def get_crew_hours(
        self,
        start_date: date,
        end_date: date,
        crew_ids: list[str] | None,
    ) -> CrewHoursResult:
        ...
```

Candidate adapters:

```text
LeonMcpReportProvider
LeonCrewExperienceProvider
LeonDutyProvider
LeonFlightEvidenceProvider
CrewHoursReconciliationService
```

Canonical internal record:

```text
crew_member_nid / login_nid
person_code
crew position
record date / interval
aircraft type
aircraft category (only after a verified rule)
block time
flight time (only if LEON defines it separately)
pic time
duty time
flight count
takeoff count
landing count
takeoff monitoring count
landing monitoring count
approaches by approach and type
dual / ICUS / training classification
source
source record ID
```

Use `loginNid` or the stable LEON identifier as the internal key. Use `personCode` for display/filtering only unless its uniqueness and immutability are verified.

## Execution plan

### S5A — Static documentation and schema map

Deliverable: `docs/architecture/leon-crew-hours-source-discovery.md`

Tasks:

- Inventory all current and historical Crew Experience fields.
- Determine the exact current arguments and return unions for `CrewMember.experienceList` through schema introspection.
- Map every requested metric to possible LEON fields.
- Record required scopes for each query.
- Catalogue MCP and report-wizard fields found in the current schema.
- Mark each conclusion as documented, inferred, or unknown.

Exit criterion: no production calculation code.

### S5B — Read-only live capability discovery

Run against sandbox or an approved operator account.

GraphQL discovery targets:

- the exact `CrewMember.experienceList` signature
- crew member lookup and stable identifiers
- `dutyList`
- FTL fields relevant to duty/FDP/work time
- MCP GraphQL fields, especially `mcp.reportWizard`
- aircraft type/category/MTOW data
- flight plus Journey Log evidence

MCP discovery targets:

- initialize the operator MCP endpoint according to its supported transport
- enumerate tools/resources/prompts if supported
- search returned capabilities for `hours`, `experience`, `work time`, `duty`, `FTL`, `logbook`, `report`, and `report wizard`
- do not call write-capable tools

Deliverable: `docs/architecture/leon-live-capability-matrix.md`

### S5C — Golden-sample reconciliation

Use one crew member and a small approved interval.

Collect:

- LEON Hrs/Work Time report export
- Crew Experience response
- Duty/FTL response
- flight/Journey Log response
- MCP/report response if available

Compare per metric:

```text
metric
LEON report value
Crew Experience value
Duty/FTL value
flight-derived value
difference
explanation/confidence
```

Required edge cases:

- multi-sector day
- PIC vs SIC/FO
- pilot flying vs pilot monitoring
- more than one landing or approach
- training / dual / ICUS
- cancelled or unconfirmed flight
- missing/unfinished Journey Log
- duplicate crew entry
- cross-midnight flight and duty
- aircraft type/category change

Exit criterion: totals match LEON or every mismatch is explained and accepted.

### S5D — Architecture decision record

Deliverable: `docs/adr/crew-hours-source-of-truth.md`

Choose one:

- direct LEON report/MCP
- Crew Experience API
- hybrid LEON sources
- local derivation

Document:

- primary source
- fallback source
- freshness behavior
- missing-data behavior
- pagination/rate limits
- identity rules
- timezone rules
- metric semantics
- auditability

### S5E — Production implementation

Only after the ADR is approved.

Implementation order:

1. Add read-only query models and parsers for the selected source.
2. Add provider adapter behind the interface.
3. Add reconciliation/audit metadata to the response.
4. Wire the existing Crew Hours endpoint.
5. Add contract, parser, aggregation, error, and regression tests.
6. Keep the old flight-evidence query as validation/fallback only if approved.

## Metric rules that remain unresolved

Do not hard-code these before reconciliation:

- whether Flight Time means block, airborne, journey-log, or report time
- whether every assigned crew member receives full block time
- PIC/SIC attribution rules
- pilot-flying vs pilot-monitoring attribution
- landing count ownership when `landingCount > 1`
- approach ownership and approach-type attribution
- training-flight classification
- dual and ICUS semantics
- Heavy classification and whether it affects totals
- Duty Time vs FDP vs Work Time
- treatment of positioning, simulator, standby, and non-flight duties
- treatment of incomplete Journey Logs

## Security and operational rules

- Read-only calls only during discovery.
- Never use `crewMember.experience.put/create/update/delete`.
- Use sandbox first.
- Do not log refresh tokens, access tokens, or complete sensitive payloads.
- Keep token refresh and retry behavior from S4.
- Add strict date-window limits and pagination controls for live probes.
- Preserve the protected stash and avoid unrelated cleanup.

## Immediate inputs still required for a full module-to-code mapping

The LEON documentation is available, but the current backend source tree is not present in this session. To produce a file-by-file implementation plan tied to the actual routes, schemas, and services, provide the backend repository or at least the Crew Hours module and current LEON client directories.

Without that code, the architecture above is grounded in the LEON documentation and the known S4 design, but exact filenames and integration points cannot be verified.
