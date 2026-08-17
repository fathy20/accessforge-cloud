# Entity — Project

A **shared operational workspace**: maintenance activity grouped under an
aircraft and a station. Projects are visible to the whole authenticated team;
`owner_id` records provenance (who created it), not access.

Every statement below is sourced from this repository.

## Shape (source: `backend/models.py::Project`)

| Field | Type | Notes |
|---|---|---|
| `id` | String(36) UUID | primary key |
| `owner_id` | String(36) FK → `users.id` | creator; provenance only, indexed (`ix_projects_owner_id`) |
| `name` | Unicode(255) | required by the API (`min_length=1`) |
| `code` | String(64), nullable | free-form reference code |
| `tail_number` | String(64), nullable | aircraft registration (UI placeholder "A6-XXX") |
| `station` | String(64), nullable | station code (UI placeholder "DXB") |
| `description` | UnicodeText, nullable | |
| `status` | String(32), default `"active"` | no lifecycle transitions implemented |
| `created_at` / `updated_at` | DateTime(tz) | Python-side defaults |

## Product intent (source: `src/routes/_authenticated/projects.tsx`)

The page subtitle reads: *"Group uploads, jobs, and tasks under aircraft /
station / check."* The create form offers Name, Tail #, Station, Description.
The UI offers creation to engineer/admin/super_admin roles and deletion to the
owner or an admin.

**Not yet implemented (verified absent):** there is no foreign key or any
other linkage from uploads, jobs, or tasks to projects in `backend/models.py`
— the grouping described by the UI copy is intent, not current schema. Do not
assume such links exist when reasoning about deletion or scoping.

## Access policy

See `MCP_Memory/api/projects.md`. Summary: all authenticated users list all
projects; creation is any authenticated user (server-side); deletion is
owner-or-admin and audited. Any future read restriction must be role-based,
not owner-based — owner-scoping would hide other engineers' aircraft projects.
