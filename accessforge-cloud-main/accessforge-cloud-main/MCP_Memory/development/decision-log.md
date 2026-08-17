# Development Decision Log

## 2026-08-17 — Projects list: shared visibility, real pagination

- **Projects list is visible to all authenticated users; pagination added;
  restriction (if ever) will be role-based.** Projects are shared operational
  workspaces (maintenance activity for an aircraft at a station — see
  `MCP_Memory/entities/project.md`), not personal records; `owner_id` is
  provenance only. Owner-scoping would hide other engineers' aircraft projects.
- `GET /api/projects` now takes `limit` (default 50, max 200) and `offset`,
  ordered `created_at DESC, id ASC` — the id tiebreaker keeps pages
  deterministic under equal timestamps. The previous bare `.limit(200)`
  silently truncated with no stable order. Contract in
  `MCP_Memory/api/projects.md`; pinned by
  `test_endpoint_authorization.py::TestProjectAuthorization`.
- Correction note: an earlier code comment justified shared visibility with a
  UI "mine" badge that does not exist (`projects.tsx` uses `mine` only to gate
  the delete button). The comment was replaced with the verified rationale
  above.
