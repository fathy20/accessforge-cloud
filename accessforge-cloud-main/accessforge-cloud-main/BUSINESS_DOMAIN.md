# Business Domain — RedSea Airlines AccessForge / REDSEA Toolkit

Inferred from the codebase, migrations, module registry, LEON integration code,
and the architecture documents under `docs/architecture/`. Verified against the
implementation, not against README claims.

## What the product is

A **web replacement for a desktop "REDSEA Toolkit"** used by RedSea Airlines'
engineering and crew-operations staff. The original tool
(`worker/redsea_toolkit.py`, preserved verbatim) was a Tkinter desktop app that
processed aviation maintenance documents. This system re-hosts those workflows
behind a FastAPI backend and a TanStack Start (React) frontend, adds
authentication/RBAC, and integrates live crew data from **LEON** (the airline's
crew-management SaaS).

## Who uses it

Airline back-office staff, on-premises, low concurrency (tens of users):

| Role | Intent |
|---|---|
| `super_admin` | Full control, including granting the super-admin role |
| `admin` | User/role management, module administration, audit review, all modules |
| `engineer` | Runs every business module including export actions |
| `viewer` | Read-only module access (no export actions) |
| `guest` | Nothing — default-deny |

Account lifecycle: self-signup lands in `pending_approval` and an admin approves
with explicit roles; admins can also create accounts directly, which start in
`password_change_required` with a one-time temporary password.

## Business modules (the registry is code-owned truth)

`backend/rbac/registry.py` defines 13 modules; the database `modules` table is
a projection of it, re-synced at startup. Business areas: maintenance, crew,
stores, admin.

**Maintenance document processing** (file upload → background job → output
download): task_extractor, task_stamping, check_control, cmp_tcm, cover_merge,
mail_merge — all mirror specific desktop-toolkit behaviors (e.g. stamping RC
card numbers derived from Boeing card numbers onto task cards; expanding
A-check codes via `CHECK_RELATIONS`).

**Deliberately not implemented** (readiness `discovery_required`): effectivity
and utilization have no real business rules yet — the standing instruction is
to *never invent rules for them* until the business supplies them.

**Crew statistics** (`crew_hours`, readiness `available`): the flagship live
module. Fetches official flight/crew duty data from LEON's MCP "Report Wizard"
report (report 57878 contract), computes per-crew block-hours summaries,
implements the approved **Augmented (Heavy) crew rules** (EVN/SVX route
override, TRN sentinel, operator-standard complement thresholds, cockpit/cabin
split), and exports a governed XLSX workbook.

**RedSea Copilot**: a chat panel that answers crew questions. It is a client of
LEON's own *Wingman* assistant (GraphQL) plus a local grounded-answer path that
reads the MCP report directly for roster/hours/heavy questions. It runs no
model of its own and only ever surfaces LEON crew data — which is why it is
authorization-gated by `crew_hours.view`.

## Critical business rules

1. **Default deny**: a permission must be explicitly granted via a role;
   modules are invisible and unrunnable without the module's view permission.
2. **Registry-projection integrity**: if the DB projection of a module
   disagrees with the code registry (tampering/drift), access fails closed.
3. **Last-super-admin protection**: the system refuses to deactivate or
   de-role the final active super-admin.
4. **Honest readiness**: modules report their true implementation state;
   unfinished modules are labeled, not faked.
5. **Grounded answers only**: Copilot/crew-hours never fabricate data — a LEON
   failure is reported as a failure, never replaced with demo data.
6. **Governed artifacts**: every upload/output passes through
   `backend/storage.py` (containment, streaming size limits, magic-byte
   validation, SHA-256, audit events).
7. **Auditability**: privileged actions (logins, role changes, approvals,
   uploads/downloads/deletes, job denials) write `audit_log` rows with
   sanitized metadata (no secrets, no PII values).

## Authoritative data

- **LEON** is authoritative for flights, duties, and crew hours; this system
  never writes to LEON (read-only integration, refresh-token → access-token).
- **The code registry** is authoritative for modules/permissions; SQL is a
  projection.
- **SQL (SQLite dev / SQL Server prod)** is authoritative for users, roles,
  uploads, jobs, projects, audit.

## Irreversible / privileged operations

Password resets (revoke sessions), account rejection, role changes, artifact
deletion, project deletion. All are permission-gated and audited.

## Known business boundaries

- **Compensation/Payroll is out of scope** until Finance/Operations provide
  explicit rules and approve (standing instruction).
- Crew Hours "Heavy" thresholds follow the operator-standard complement rules
  recorded in `docs/architecture/leon-live-capability-matrix.md` and the crew
  hours assessments.
