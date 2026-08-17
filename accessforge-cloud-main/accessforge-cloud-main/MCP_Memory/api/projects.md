# API — Projects (`backend/project_routes.py`)

## Endpoints

| Method | Path | Auth | Behavior |
|---|---|---|---|
| GET | `/api/projects` | any authenticated user | Paginated list of **all** projects (shared visibility) |
| POST | `/api/projects` | any authenticated user | Create; `owner_id` set to the caller |
| DELETE | `/api/projects/{project_id}` | owner or admin/super_admin role | Delete + `audit_log` row; 404 unknown id, 403 otherwise |

Note: the UI shows the create form only to engineer/admin/super_admin, but the
server accepts creation from any authenticated user — a known looseness, not a
documented guarantee.

## Access policy (pinned by tests)

Projects are shared operational workspaces (see
`MCP_Memory/entities/project.md`), **not** personal records:

- Every authenticated user sees every project; `owner_id` is provenance only.
- Owner-based read filtering is explicitly rejected. If listing ever needs
  restricting, it must be **role-based** (RBAC permission), not owner-based.
- Unauthenticated requests are 401.

Pinned in `backend/tests/test_endpoint_authorization.py::TestProjectAuthorization`
(`test_projects_are_visible_to_every_authenticated_user`,
`test_unauthenticated_project_list_is_rejected`).

## Pagination contract (GET `/api/projects`)

- Query params: `limit` (default 50, `1 <= limit <= 200`) and `offset`
  (default 0, `>= 0`). Out-of-bounds values are a 422, never clamped.
- Ordering: `created_at DESC, id ASC` — newest first, with `id` as a
  deterministic tiebreaker so pages are stable when timestamps collide.
- There is no total-count field; clients page until a short page returns.

## Response item shape (pinned; additive changes only)

```json
{
  "id": "…", "owner_id": "…", "name": "…", "code": null,
  "tail_number": null, "station": null, "description": null,
  "status": "active", "created_at": "…"
}
```

`tail_number` and `station` were added 2026-08-17 (migration `c9d0e1f2a3b4`);
the seven original fields (`id`, `owner_id`, `name`, `code`, `description`,
`status`, `created_at`) are the frozen baseline.
