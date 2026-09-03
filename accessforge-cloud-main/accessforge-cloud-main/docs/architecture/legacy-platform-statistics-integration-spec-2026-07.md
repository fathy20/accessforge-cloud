# RedSea Platform Architecture & Future Statistics Integration Specification

**Document Type:** Architecture and Integration Specification  
**Target System:** RedSea Main Platform  
**Future Sector:** Statistics  
**First Planned Module:** Crew Hours  
**Status:** Planning and Architecture Preparation  
**Audience:** RedSea system architects, backend developers, frontend developers, database engineers, DevOps engineers, QA engineers, and future coding agents

---

# 1. Purpose of This Document

This document explains how the main RedSea platform must be prepared for a future **Statistics Sector** and its first operational module, **Crew Hours**.

The Crew Hours module will initially be developed as an independent Proof of Concept so the team can safely validate:

- Leon API authentication;
- Leon API permissions;
- the real Leon response contract;
- crew-flight data retrieval;
- time-zone behaviour;
- data mapping;
- duplicate prevention;
- business rules;
- block-hours calculations;
- Excel export;
- dashboard requirements.

After the independent module is validated, it will be integrated into the main RedSea platform.

The main RedSea system must therefore be designed now in a way that allows this future integration without:

- rewriting the core platform architecture;
- redesigning the database;
- replacing the routing system;
- rebuilding the permissions model;
- breaking existing modules;
- duplicating Leon integration code;
- creating direct dependencies between the frontend and Leon API.

This document does not require the RedSea team to build the full Statistics Sector immediately.

It requires the team to make the current architecture **ready for the future sector**.

---

# 2. Executive Summary

The future RedSea platform should be treated as a modular business platform, not a collection of unrelated pages.

The intended high-level structure is:

```text
RedSea Platform
├── Dashboard
├── Operations
├── Engineering
├── Inventory
├── Administration
└── Statistics
    ├── Overview
    ├── Crew Hours
    ├── Crew Days
    ├── Aircraft Utilisation
    ├── Route Statistics
    ├── Delay Analysis
    ├── FTL Statistics
    ├── Crew Performance
    ├── Export Centre
    ├── Sync History
    └── Exceptions
```

The first Statistics module will be:

```text
Statistics
└── Crew Hours
```

Its main data source will be Leon Software.

The target data flow is:

```text
Leon API
    ↓
Leon Integration Adapter
    ↓
Raw Response Storage
    ↓
Mapping and Normalisation
    ↓
Internal Domain Models
    ↓
Business Rules
    ↓
Database
    ↓
Statistics Services
    ↓
Dashboard and Excel Export
```

The main platform must never depend directly on Leon response field names.

---

# 3. Scope

## 3.1 Included in This Specification

This document covers:

- future Statistics sector architecture;
- Crew Hours module integration requirements;
- backend module organisation;
- frontend navigation and routing preparation;
- database expansion strategy;
- integration-layer design;
- job-system compatibility;
- authentication and authorisation requirements;
- audit and logging requirements;
- reporting and export architecture;
- future Crew Days integration;
- migration from standalone PoC into RedSea;
- non-negotiable architecture rules;
- expected database entities and relationships;
- API namespace planning;
- testing and acceptance expectations.

---

## 3.2 Not Included in the Current Main-System Work

The main RedSea team is not currently required to implement:

- the Leon API connector;
- live Leon synchronisation;
- Crew Hours calculations;
- Cockpit and Cabin summaries;
- Crew Days;
- FTL rules;
- Excel report generation;
- scheduled Leon jobs;
- advanced Statistics dashboards.

These components will first be validated separately.

The current requirement is to prevent the main architecture from blocking them later.

---

# 4. Business Background

The current Crew Hours process is based on flight and crew data that can be exported from Leon.

The source data contains information similar to:

```text
Position type
Name
Surname
Date
Aircraft
Flight number
Departure airport
Arrival airport
OFF
ON
Block time
```

The expected business output contains four Excel sheets:

```text
Cockpit
Cockpit Summary
Cabin
Cabin Summary
```

Each crew member must have:

- a detailed list of flights;
- total flight count;
- total block hours;
- position classification;
- monthly summary;
- exceptions where applicable.

The system must later support additional classifications such as:

```text
PAD
Training
Maintenance
Ground
Not Active
Standby
Leave
OFF
Sick
Duty
```

Not all classifications should be included automatically in Crew Hours totals.

Business policies for PAD, Training, and other special activities must be approved separately.

---

# 5. Why the Module Is Being Built Separately First

The independent PoC reduces risk.

At the moment, several Leon-specific details must be proven through real API responses:

- authentication mechanism;
- token lifetime;
- endpoint or GraphQL operation;
- field names;
- nested object structure;
- stable identifiers;
- pagination;
- request limits;
- time-zone semantics;
- cancelled-flight behaviour;
- duplicate records;
- crew-role values;
- aircraft-selection behaviour.

Building directly inside RedSea before these details are confirmed would mix external-integration uncertainty with main-platform development.

The separate PoC acts as a validation environment.

However, it must be built with the same architectural principles required by RedSea so that the core components can be moved later.

---

# 6. Platform Architecture Principles

The RedSea platform should follow these principles.

## 6.1 Modular Monolith

Use a modular monolith unless a clear technical requirement justifies a separate service.

The Statistics sector should be logically independent but may remain deployed within the same backend application.

Recommended conceptual structure:

```text
backend/
├── core/
├── integrations/
├── modules/
├── jobs/
├── exports/
├── security/
└── shared/
```

---

## 6.2 Domain Separation

Each business module must own its business logic.

Examples:

```text
modules/statistics/crew_hours
modules/statistics/crew_days
modules/engineering/task_stamping
modules/operations/...
```

Statistics business logic must not be placed in:

```text
utils/
helpers/
common miscellaneous services/
frontend components/
Leon client files/
```

---

## 6.3 Provider Isolation

Leon is an external provider.

The system must use:

```text
Leon API
→ Leon Adapter
→ Internal Domain Models
```

It must not use:

```text
Leon API
→ Frontend

Leon API
→ Database tables copied directly from Leon schema

Leon API
→ Crew Hours calculations inside the HTTP client
```

---

## 6.4 Internal Models Are the System Contract

The RedSea database and services must depend on internal fields such as:

```text
crew_member_id
flight_id
operational_date
off_time
on_time
block_minutes
position_type
classification
included_in_total
```

Leon field names must exist only inside the integration and mapping layers.

---

## 6.5 Duration Storage

All durations must be stored as integer minutes.

Examples:

```text
05:25 → 325 minutes
57:35 → 3455 minutes
```

Do not store block totals as normal clock strings.

Formatting to `HH:MM` happens only in:

- frontend responses;
- dashboard presentation;
- Excel export;
- PDF or printed reports.

This prevents totals above 24 hours from wrapping incorrectly.

---

## 6.6 Idempotency

Repeated synchronisation of the same Leon period must not duplicate records or inflate totals.

The system must use:

- stable Leon IDs where available;
- database unique constraints;
- idempotent upsert logic;
- source-payload hashes where useful;
- automated duplicate-sync tests.

---

# 7. Future Statistics Sector

The main platform must support a first-class sector named:

```text
Statistics
```

It is not a single page and must not be implemented as a utility screen.

Expected future modules:

```text
Statistics
├── Overview
├── Crew Hours
├── Crew Days
├── Aircraft Utilisation
├── Route Statistics
├── Delay Analysis
├── FTL Statistics
├── Crew Performance
├── Export Centre
├── Sync History
└── Exceptions
```

The sidebar, permissions, route structure, and database strategy must allow new modules to be added without redesigning the platform.

---

# 8. Main-System Frontend Requirements

## 8.1 Sidebar Structure

The sidebar must support grouped sectors and nested modules.

Future example:

```text
Statistics
├── Overview
├── Crew Hours
├── Crew Days
├── Aircraft Utilisation
├── Routes
├── FTL
├── Exports
└── Sync History
```

The Statistics menu may remain hidden until the first module is ready.

Do not create an empty visible menu for normal users unless product management approves it.

---

## 8.2 Route Namespace

Reserve the following route namespace:

```text
/statistics
/statistics/overview
/statistics/crew-hours
/statistics/crew-days
/statistics/aircraft-utilisation
/statistics/routes
/statistics/ftl
/statistics/exports
/statistics/sync-history
/statistics/exceptions
```

Recommended feature location:

```text
frontend/src/
├── features/
│   └── statistics/
│       ├── shared/
│       ├── crew-hours/
│       ├── crew-days/
│       └── utilisation/
└── routes/
    └── statistics/
```

Do not put all Statistics screens in one oversized component.

---

## 8.3 Frontend Access Control

Frontend route protection must reflect backend permissions.

Frontend checks are for user experience only.

The backend remains the authority.

Example permission checks:

```text
statistics.view
statistics.crew_hours.view
statistics.crew_hours.export
statistics.crew_hours.sync
statistics.admin
```

The frontend must never receive Leon tokens.

The frontend must communicate only with RedSea backend APIs.

---

## 8.4 Shared Statistics Components

The platform may later need reusable components for:

- date-range filters;
- month selector;
- crew selector;
- aircraft selector;
- route selector;
- KPI cards;
- data tables;
- export dialogs;
- sync-status badges;
- exception banners;
- empty states;
- loading states;
- permission-denied states.

These should be shared inside the Statistics feature, not made globally generic before real reuse exists.

---

# 9. Main-System Backend Requirements

Recommended backend structure:

```text
backend/
└── app/
    ├── core/
    │   ├── config.py
    │   ├── database.py
    │   ├── logging.py
    │   └── exceptions.py
    │
    ├── integrations/
    │   └── leon/
    │       ├── auth.py
    │       ├── client.py
    │       ├── schemas.py
    │       ├── mapper.py
    │       ├── crew_flights.py
    │       ├── crew_days.py
    │       └── exceptions.py
    │
    ├── modules/
    │   └── statistics/
    │       ├── shared/
    │       ├── crew_hours/
    │       │   ├── models.py
    │       │   ├── schemas.py
    │       │   ├── repository.py
    │       │   ├── service.py
    │       │   ├── calculations.py
    │       │   ├── classification.py
    │       │   ├── aggregation.py
    │       │   └── routes.py
    │       │
    │       ├── crew_days/
    │       └── utilisation/
    │
    ├── jobs/
    ├── exports/
    ├── security/
    └── api/
```

The exact folders may be adapted to the existing RedSea structure.

The critical requirement is the separation of:

```text
external provider
domain logic
persistence
HTTP API
exports
frontend
```

---

# 10. Leon Integration Layer

## 10.1 Responsibility

The Leon integration layer owns:

- authentication;
- token refresh;
- request headers;
- request timeouts;
- pagination;
- provider-specific response schemas;
- Leon error conversion;
- response sanitisation;
- field mapping.

It does not own:

- monthly totals;
- Cockpit versus Cabin policy;
- PAD inclusion rules;
- dashboard filters;
- Excel formatting;
- RedSea permissions.

---

## 10.2 Secrets

In the PoC, Leon secrets should be stored in backend environment variables.

In the main RedSea deployment, use the platform's established secret-management mechanism.

Examples:

```text
server environment variables
Docker secrets
cloud secret manager
deployment secret store
```

Never store secrets in:

```text
React environment variables
localStorage
sessionStorage
database plaintext fields
Git
application logs
Excel exports
API responses
```

---

## 10.3 Error Mapping

Provider errors must be converted to internal errors.

Examples:

```text
LeonAuthenticationError
LeonPermissionError
LeonRateLimitError
LeonValidationError
LeonTransportError
LeonContractError
```

The frontend should receive safe errors such as:

```json
{
  "code": "LEON_PERMISSION_DENIED",
  "message": "The Leon integration does not have permission to read crew-flight data."
}
```

Do not expose raw authorisation headers, tokens, or sensitive provider payloads.

---

# 11. Database Architecture

The main system must allow new Statistics tables without changing unrelated modules.

The following entities are expected.

---

## 11.1 Integration Configuration

Suggested table:

```text
integration_configs
```

Purpose:

- store provider metadata;
- identify active integration;
- store configuration references;
- track last successful connection test;
- support future external providers.

Suggested fields:

```text
id
provider
name
is_active
configuration_reference
selected_resources
selected_aircraft
last_tested_at
last_successful_sync_at
created_at
updated_at
```

Do not store the Leon token in plaintext.

---

## 11.2 Sync Runs

Suggested table:

```text
sync_runs
```

Purpose:

- record every manual or scheduled data import;
- support troubleshooting;
- expose sync history;
- provide audit information.

Suggested fields:

```text
id
provider
module
sync_type
requested_by_user_id
start_date
end_date
status
requested_at
started_at
completed_at
records_received
records_created
records_updated
records_skipped
records_failed
exception_count
safe_error_code
safe_error_message
correlation_id
created_at
updated_at
```

Recommended statuses:

```text
queued
running
completed
partially_completed
failed
cancelled
```

---

## 11.3 Crew Members

Suggested table:

```text
crew_members
```

Suggested fields:

```text
id
leon_id
crew_code
first_name
middle_name
surname
display_name
position_type
employment_status
is_active
source_updated_at
created_at
updated_at
```

Rules:

- do not use the person's name as a unique key;
- use Leon stable ID when available;
- allow a crew member's position or status to change;
- preserve source identity separately from display fields.

---

## 11.4 Aircraft

If RedSea already has a central aircraft table, reuse it.

Do not create a duplicate Statistics-only aircraft master unless required.

Expected information:

```text
id
leon_id
registration
aircraft_type
fleet
is_active
created_at
updated_at
```

Create a mapping table if RedSea and Leon use different aircraft IDs.

---

## 11.5 Airports

If the platform already has airport data, reuse it.

Otherwise a minimal table may contain:

```text
id
icao_code
iata_code
name
country_code
timezone
created_at
updated_at
```

Airport time zones may later assist with time validation, but they must not be used to invent the meaning of Leon timestamps.

---

## 11.6 Flights

Suggested table:

```text
flights
```

Suggested fields:

```text
id
leon_id
flight_number
operational_date
aircraft_id
aircraft_registration_snapshot
aircraft_type_snapshot
departure_airport_id
arrival_airport_id
adep_code
ades_code
scheduled_departure
scheduled_arrival
source_off_time
source_on_time
source_timezone
source_utc_offset
off_time_utc
on_time_utc
timezone_status
block_minutes
flight_status
source_updated_at
raw_payload_hash
created_at
updated_at
```

Do not fill UTC fields until the source time semantics are confirmed.

Suggested timezone-status values:

```text
confirmed_utc
confirmed_local
converted_to_utc
timezone_unknown
ambiguous
```

---

## 11.7 Crew Flight Assignments

Suggested table:

```text
crew_flight_assignments
```

Suggested fields:

```text
id
leon_id
crew_member_id
flight_id
position_type
duty_role
classification
block_minutes
included_in_total
exclusion_reason
business_rule_status
source_updated_at
raw_payload_hash
sync_run_id
created_at
updated_at
```

This is the central Crew Hours table.

It links a crew member to a flight and records how that assignment is treated by the business rules.

---

## 11.8 Raw Integration Payloads

Suggested table:

```text
integration_raw_records
```

Purpose:

- retain source evidence;
- troubleshoot mapping problems;
- compare provider changes;
- support contract migration.

Suggested fields:

```text
id
provider
entity_type
source_entity_id
sync_run_id
payload_json
payload_hash
schema_version
fetched_at
sanitisation_status
created_at
```

Raw records must be protected and should contain only data necessary for the module.

Do not store travel documents, passports, APIS information, or unrelated personal data.

---

## 11.9 Classification Rules

Suggested table or configuration source:

```text
statistics_classification_rules
```

Suggested fields:

```text
id
module
rule_code
source_value
normalised_classification
position_type
included_in_total
status
effective_from
effective_to
approved_by_user_id
approved_at
notes
created_at
updated_at
```

This supports controlled rules such as PAD and Training.

---

## 11.10 Exceptions

Suggested table:

```text
statistics_exceptions
```

Suggested fields:

```text
id
module
entity_type
entity_id
sync_run_id
exception_code
severity
message
details_json
status
resolved_by_user_id
resolved_at
created_at
updated_at
```

Examples:

```text
MISSING_OFF_TIME
MISSING_ON_TIME
UNKNOWN_TIMEZONE
NEGATIVE_DURATION
BLOCK_TIME_MISMATCH
UNKNOWN_POSITION
UNAPPROVED_CLASSIFICATION
DUPLICATE_SOURCE_RECORD
```

Do not silently remove anomalous records.

---

## 11.11 Monthly Summaries

Initially, summaries may be calculated from assignment data.

If performance later requires storage, use:

```text
crew_monthly_summaries
```

Suggested fields:

```text
id
crew_member_id
year
month
position_type
total_block_minutes
flight_count
pad_minutes
training_minutes
excluded_minutes
exception_count
calculation_version
last_calculated_at
created_at
updated_at
```

Derived tables must always be rebuildable from source assignments.

---

# 12. Database Relationships

Expected logical relationships:

```text
users
  └── sync_runs.requested_by_user_id

integration_configs
  └── sync_runs

sync_runs
  ├── integration_raw_records
  ├── crew_flight_assignments
  └── statistics_exceptions

crew_members
  └── crew_flight_assignments

aircraft
  └── flights

flights
  └── crew_flight_assignments

classification_rules
  └── crew_flight_assignments.business treatment

crew_members
  └── crew_monthly_summaries
```

Recommended uniqueness:

```text
crew_members.leon_id
flights.leon_id
crew_flight_assignments.leon_id
```

Where Leon does not provide a stable assignment ID, use an approved composite uniqueness key.

Possible fallback:

```text
crew_member_leon_id
flight_leon_id
position_type
source_off_time
```

The actual key must be confirmed during Leon discovery.

---

# 13. Database Migration Strategy

The main RedSea team should not create all future tables immediately unless needed.

However, it must:

- keep migrations modular;
- avoid table-name collisions;
- reserve a Statistics naming convention;
- support adding foreign keys to central user, aircraft, and permission tables;
- avoid embedding module-specific fields into unrelated core tables.

Recommended migration phases:

```text
Phase A:
integration_configs
sync_runs

Phase B:
crew_members
flights
crew_flight_assignments
integration_raw_records

Phase C:
classification_rules
statistics_exceptions

Phase D:
crew_monthly_summaries if required
```

Every migration must include a downgrade plan where the project's migration policy supports it.

---

# 14. API Namespace

Reserve:

```text
/api/statistics
/api/integrations/leon
```

Expected future endpoints:

```http
POST /api/integrations/leon/test
POST /api/integrations/leon/sync/crew-flights
POST /api/integrations/leon/sync/crew-days

GET /api/statistics/crew-hours/overview
GET /api/statistics/crew-hours/crew
GET /api/statistics/crew-hours/crew/{crew_member_id}
GET /api/statistics/crew-hours/flights
GET /api/statistics/crew-hours/exceptions
GET /api/statistics/sync-runs
POST /api/statistics/crew-hours/export
```

Do not expose Leon's API schema as the RedSea API.

The RedSea API should return stable internal response models.

---

# 15. Permissions and Roles

The existing RedSea permissions architecture must support module-level and action-level permissions.

Recommended permission set:

```text
statistics.view
statistics.overview.view

statistics.crew_hours.view
statistics.crew_hours.export
statistics.crew_hours.sync
statistics.crew_hours.manage_rules

statistics.crew_days.view
statistics.crew_days.sync

statistics.sync_history.view
statistics.exceptions.view
statistics.exceptions.resolve

statistics.admin
```

Recommended role examples:

```text
Statistics Viewer
Statistics Analyst
Statistics Operator
Statistics Administrator
System Administrator
```

Principles:

- viewing must not automatically grant synchronisation;
- export may be separately restricted;
- business-rule approval should be tightly restricted;
- Leon secret configuration must be administrator-only;
- backend permission checks are mandatory.

---

# 16. Job-System Integration

The main RedSea system already contains a job concept.

The future Statistics modules should reuse the central job system if it supports:

- typed job names;
- status tracking;
- requested user;
- progress metadata;
- safe failures;
- output-file references;
- retry policy;
- cancellation where applicable.

Expected job types:

```text
LEON_CREW_FLIGHTS_SYNC
LEON_CREW_DAYS_SYNC
CREW_HOURS_MONTHLY_AGGREGATION
CREW_HOURS_EXCEL_EXPORT
STATISTICS_EXCEPTION_RECHECK
STATISTICS_DATA_CLEANUP
```

Do not add Celery, Redis, RabbitMQ, or a separate queue only for this module unless the existing job infrastructure proves insufficient.

The first PoC may run small syncs synchronously.

The main-system design should allow long jobs to run in the existing worker layer later.

---

# 17. Audit Requirements

The following actions must be auditable:

- Leon connection test;
- manual synchronisation;
- scheduled synchronisation;
- export generation;
- business-rule changes;
- exception resolution;
- integration configuration changes;
- Statistics permission changes.

Audit information should include:

```text
user
action
module
entity
timestamp
correlation_id
safe metadata
success or failure
```

Never store tokens in audit records.

---

# 18. Logging and Observability

Structured logging should include:

```text
correlation_id
job_id
sync_run_id
provider
module
date range
records received
records created
records updated
records skipped
exceptions
elapsed time
safe error code
```

Logs must exclude:

```text
Leon refresh token
Leon access token
Authorization headers
passwords
unnecessary personal information
travel documents
passport details
```

The main monitoring view should later show:

- last successful sync;
- last failed sync;
- data freshness;
- pending exceptions;
- record count;
- sync duration;
- provider availability.

---

# 19. Crew Hours Business Logic

## 19.1 Normal Flight Assignments

Expected normal classifications:

```text
cockpit_flight
cabin_flight
```

Normal Cockpit flight records contribute to Cockpit totals.

Normal Cabin flight records contribute to Cabin totals.

---

## 19.2 PAD

PAD should initially be treated as:

```text
classification = positioning
included_in_total = false
business_rule_status = pending
```

This default remains until an authorised RedSea business owner approves a different rule.

---

## 19.3 Training

Training should initially be treated as:

```text
classification = training
included_in_total = false
business_rule_status = pending
```

It must remain visible in details and exceptions.

---

## 19.4 Maintenance and Ground

Suggested initial treatment:

```text
maintenance
ground
```

These records must not enter Cockpit or Cabin flight-block totals.

They may later support separate statistics.

---

## 19.5 Unknown Values

Unknown position or activity values must not be silently mapped to normal flight.

Use:

```text
classification = unknown
included_in_total = false
```

Create an exception for review.

---

# 20. Time and Time-Zone Rules

Do not assume that Leon timestamps are UTC.

During discovery, compare:

- Leon API response;
- Leon user interface;
- Leon Excel export;
- a known real flight.

Store source values separately.

Recommended fields:

```text
source_off_time
source_on_time
source_timezone
source_utc_offset
off_time_utc
on_time_utc
timezone_status
```

Non-negotiable rule:

```text
Never append Z, assume UTC, or convert timestamps until the source semantics are confirmed.
```

If Leon provides a verified block duration, it may be used as the primary business value.

OFF and ON timestamps should be used for validation.

If block duration is absent, it may be calculated only after timestamp semantics are confirmed.

---

# 21. Export Architecture

The future export engine should be a backend component.

Recommended location:

```text
backend/app/exports/
```

For Crew Hours, the recommended library is:

```text
openpyxl
```

Expected workbook:

```text
Crew_Hours_YYYY-MM.xlsx
```

Required sheets:

```text
Cockpit
Cockpit Summary
Cabin
Cabin Summary
```

Optional future sheets:

```text
Exceptions
Raw Data
Sync Metadata
```

Excel requirements:

- freeze header row;
- filters enabled;
- readable column widths;
- consistent dates;
- duration totals above 24 hours;
- report period;
- generated-at timestamp;
- no secrets;
- no core calculations dependent on Excel formulas.

For Excel duration values, use a format that supports more than 24 hours:

```text
[hh]:mm
```

---

# 22. Dashboard Architecture

The future Crew Hours dashboard will include:

## Filters

```text
Month
Date range
Crew member
Position type
Aircraft
Aircraft type
Flight number
ADEP
ADES
Classification
```

## KPI Cards

```text
Total Cockpit Hours
Total Cabin Hours
Cockpit Crew Count
Cabin Crew Count
Total Flights
Average Hours per Crew
Top Crew Member
Exception Count
Last Leon Sync
```

## Pages

```text
Overview
Cockpit Details
Cockpit Summary
Cabin Details
Cabin Summary
Exceptions
Sync History
Exports
```

## Charts

Useful charts may include:

```text
Cockpit vs Cabin Hours
Hours by Crew
Hours by Day
Hours by Aircraft
Hours by Route
Top Ten Crew Members
Monthly Trend
```

The main-system layout should support these pages without requiring a special new frontend framework.

---

# 23. Crew Days Future Module

Crew Days will be a separate module.

Its expected classifications may include:

```text
OFF
Standby
Training
Leave
Sick
Duty
Positioning
Other roster activity
```

Crew Days must not replace Crew Hours.

The relationship is:

```text
Crew Flights
→ flight assignments and block hours

Crew Days
→ daily roster and duty classification
```

Future combined analytics may compare:

```text
block hours
duty days
standby days
OFF days
training days
leave days
utilisation
```

The database should therefore avoid encoding all crew activity into only the crew-flight-assignment table.

A future structure may include:

```text
crew_day_records
crew_daily_status
crew_duty_periods
```

---

# 24. Future Aircraft Utilisation

The Statistics sector may later calculate:

- block hours by aircraft;
- sectors by aircraft;
- utilisation by day;
- utilisation by month;
- aircraft downtime;
- route distribution;
- fleet comparison.

The Flight and Aircraft models used for Crew Hours should therefore be reusable.

Do not create Crew Hours-specific copies of aircraft and flight entities when central entities are appropriate.

---

# 25. Future Route Statistics

The existing flight model should support route-level analysis:

```text
ADEP
ADES
route key
operational date
aircraft
flight number
block duration
status
```

Future statistics may include:

- flights by route;
- average block time;
- most-used routes;
- Cockpit and Cabin hours by route;
- seasonal trends;
- delay comparison.

---

# 26. Future FTL Statistics

FTL is not part of Phase 1.

However, the architecture should allow later use of:

- duty start and end;
- block hours;
- sectors;
- standby;
- rest;
- cumulative limits;
- exceptions.

FTL calculations must be developed as a separate approved rules engine.

Do not place FTL rules inside Crew Hours calculation files.

---

# 27. Authentication for Real Crew Data

The standalone PoC may begin with local development endpoints.

Before real crew data is shown in a frontend, authentication is mandatory.

The main RedSea integration will use:

```text
RedSea Authentication
RedSea Roles
RedSea Permissions
RedSea Audit Logs
```

No separate permanent authentication system should survive after integration.

The PoC authentication, if created, must be removable and isolated.

---

# 28. Data Privacy

The module handles employee operational data.

Only collect information necessary for Statistics.

Do not retrieve or store:

- passports;
- visas;
- travel documents;
- APIS documents;
- personal document scans;
- unrelated contact data;
- unrelated HR information.

Apply least-privilege access.

Exports must be limited to authorised users.

Raw integration payloads should be protected and retained only according to an approved policy.

---

# 29. PoC-to-RedSea Integration Strategy

The independent PoC will contain several reusable components.

Expected mapping:

```text
PoC Leon authentication
→ backend/app/integrations/leon/auth.py

PoC Leon client
→ backend/app/integrations/leon/client.py

PoC response schemas
→ backend/app/integrations/leon/schemas.py

PoC mapper
→ backend/app/integrations/leon/mapper.py

PoC Crew Hours calculations
→ backend/app/modules/statistics/crew_hours/calculations.py

PoC classification logic
→ backend/app/modules/statistics/crew_hours/classification.py

PoC export engine
→ backend/app/exports/crew_hours_excel.py

PoC frontend pages
→ frontend Statistics feature
```

Components that should not be copied directly:

- PoC-specific authentication;
- PoC SQLite configuration;
- temporary local file paths;
- development-only API routes;
- temporary test users;
- experimental debugging code;
- hardcoded sample responses.

---

# 30. Integration Preconditions

Do not merge the PoC into RedSea until all of the following are proven:

1. real Leon authentication succeeds;
2. a real sanitised one-day response is stored;
3. field mapping is documented;
4. pagination is confirmed;
5. time-zone semantics are confirmed or safely marked unresolved;
6. stable identifiers are known;
7. idempotent synchronisation passes;
8. Cockpit and Cabin separation is validated;
9. core totals match an approved sample;
10. the required Excel workbook is validated;
11. secrets do not appear in logs, Git, frontend, or exports;
12. real frontend data is protected by authentication;
13. business-rule decisions are documented;
14. core automated tests pass.

---

# 31. Non-Negotiable Execution Gates

## Gate 1 — Leon Contract

```text
No real Leon contract
→ no production mapper
```

A mock response cannot prove the provider contract.

---

## Gate 2 — Time Zone

```text
No confirmed time semantics
→ no assumed UTC conversion
```

---

## Gate 3 — Stable Identity

```text
No stable source identifiers
→ no accepted production-style upsert
```

---

## Gate 4 — Business Policy

```text
No approved PAD or Training policy
→ exclude from totals and mark pending
```

---

## Gate 5 — Data Protection

```text
No authentication
→ no real crew data in the frontend
```

---

## Gate 6 — Idempotency

```text
No duplicate-sync test
→ no monthly sync acceptance
```

---

## Gate 7 — Export Validation

```text
No approved Excel comparison
→ no Phase 1 acceptance
```

---

# 32. Testing Requirements for Main-System Integration

## Unit Tests

- duration conversion;
- HH:MM formatting;
- midnight crossing;
- classification;
- business-rule inclusion;
- monthly aggregation;
- uniqueness-key generation;
- Leon-to-domain mapping;
- safe error conversion;
- export formatting.

## Integration Tests

```text
sanitised Leon fixture
→ mapper
→ database
→ Crew Hours service
→ API
→ export
```

## Idempotency Test

Run the same sync twice.

Expected:

```text
no duplicate assignments
no doubled total
second run reports updates or skips correctly
```

## Permission Tests

Verify:

- view-only users cannot sync;
- users without export permission cannot export;
- unauthorised users cannot view crew data;
- only approved roles can change rules;
- only administrators can manage the integration.

## Security Tests

Verify:

- tokens do not appear in logs;
- tokens are not returned by APIs;
- frontend bundles contain no Leon secrets;
- exports contain no integration credentials;
- errors are sanitised.

---

# 33. Expected Main-System Work Now

The RedSea main-system team should now:

1. review the existing backend structure;
2. identify the correct future location for `integrations/leon`;
3. identify the correct future location for `modules/statistics`;
4. ensure sidebar grouping can support Statistics;
5. ensure route guards can support new permissions;
6. ensure the job system can register future Statistics job types;
7. ensure database migrations can add the expected entities;
8. avoid using reserved Statistics route names for other features;
9. avoid coupling shared flight or aircraft entities to one module;
10. document any current architecture conflict.

The team should not build speculative Leon schemas.

---

# 34. Questions the Main-System Team Must Answer

Before future integration, document answers to:

## Backend

- Where should integration adapters live?
- How are module routers registered?
- How are service dependencies injected?
- How are long jobs executed?
- How are generated files stored and downloaded?
- How are audit events recorded?

## Database

- Does the system already have Crew, Aircraft, Airport, or Flight tables?
- Which tables are authoritative?
- Can Leon IDs be added safely?
- What uniqueness strategy is currently used?
- Are JSON fields supported?
- How are migrations versioned and reviewed?

## Frontend

- How are sectors and sidebar groups declared?
- How are route permissions enforced?
- How are large server-side tables handled?
- What chart library is already used?
- What export-download pattern exists?

## Security

- How are secrets managed in deployment?
- How are permissions named?
- Which role will manage Leon sync?
- Which users may export crew information?
- What audit policy applies?

---

# 35. Required Architecture Review Output

After reviewing this specification, the main-system coding agent or engineer should return:

```text
1. Existing architecture summary
2. Relevant files inspected
3. Current database entities that can be reused
4. Proposed Statistics module locations
5. Proposed Leon integration location
6. Routing compatibility
7. Sidebar compatibility
8. Permissions compatibility
9. Job-system compatibility
10. Export-system compatibility
11. Database migration impact
12. Conflicts and risks
13. Required preparatory changes
14. Changes that should not be made yet
15. Readiness decision
```

The readiness decision must be one of:

```text
ARCHITECTURE READY

READY WITH MINOR PREPARATION

REQUIRES STRUCTURAL CHANGES

BLOCKED BY CURRENT DATABASE DESIGN

BLOCKED BY CURRENT PERMISSIONS DESIGN

INSUFFICIENT INFORMATION
```

---

# 36. Instructions for the Main-System Coding Agent

You are not being asked to implement the Statistics sector now.

Your task is to inspect the existing RedSea system and evaluate whether it can support the future architecture described in this document.

You must:

- inspect real code before answering;
- inspect the existing SQLAlchemy models;
- inspect migrations;
- inspect route registration;
- inspect authentication and permission logic;
- inspect sidebar configuration;
- inspect the job system;
- inspect file export handling;
- identify reusable entities;
- identify naming conflicts;
- identify migration risks;
- propose the smallest preparatory changes.

You must not:

- invent the existing architecture;
- create speculative Leon fields;
- create empty Statistics tables without need;
- rewrite the main system;
- introduce Redis, Celery, or microservices without evidence;
- add a visible empty Statistics menu without approval;
- expose Leon credentials;
- start Crew Hours implementation;
- change unrelated modules.

---

# 37. Final Target Architecture

The final integrated architecture should look conceptually like:

```text
RedSea Frontend
    ↓
RedSea Statistics API
    ↓
Crew Hours Application Service
    ↓
Crew Hours Domain Logic
    ↓
Repositories
    ↓
RedSea Database
    ↑
Leon Mapper
    ↑
Leon Integration Client
    ↑
Leon API
```

Exports follow:

```text
Crew Hours Service
    ↓
Export Service
    ↓
Excel File
    ↓
Protected Download
```

Jobs follow:

```text
User or Schedule
    ↓
RedSea Job System
    ↓
Leon Sync Service
    ↓
Sync Run and Audit
```

---

# 38. Final Architecture Rules

The RedSea platform must remain:

```text
modular
provider-independent
secure
testable
idempotent
auditable
extensible
```

The Statistics sector must be added as a normal platform sector, not a special application attached beside RedSea.

The Leon API must be treated as an external provider behind an adapter.

Crew Hours must own its business rules.

Durations must be stored as integer minutes.

Real crew data must be protected by RedSea authentication and permissions.

Business classifications must be approved and traceable.

The PoC must prove the workflow before integration.

The main RedSea system must prepare for this future without implementing speculative provider logic today.

---

# 39. Immediate Action Request

Perform an architecture-readiness review of the current RedSea project against this document.

Do not implement Crew Hours yet.

Return:

- exact files inspected;
- current architecture findings;
- database compatibility;
- recommended future folder locations;
- permission and routing readiness;
- job-system readiness;
- required minimal preparatory changes;
- risks;
- final readiness decision.

The current objective is:

```text
Make RedSea ready for future Statistics integration
without disturbing the work already in progress.
```
