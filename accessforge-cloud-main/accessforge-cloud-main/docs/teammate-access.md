> **CANCELLED — 2026-08-19, by owner ruling.** No account is to be created on
> the operator's instance. A teammate runs the stack on their own machine
> against their own empty database, and creates their own account there with
> `python -m backend.tools.create_local_user`; see
> `docs/onboarding-local-setup.md`. Nothing described below was ever
> provisioned: the five accounts on this instance are unrelated to it.
>
> Kept for the role analysis in sections 2-4, which still documents what
> `viewer` grants and the `POST /api/jobs` sharp edge. Section 6
> (provisioning) is void.

# Teammate access — frontend design account

Written 2026-08-19. Verified against the repository and the local `redsea.db` on
that date. The account described here is **queued for the owner**; nothing is
provisioned by this document.

---

## 1. What the account is for

A teammate doing **frontend design work** — layout, styling, component and
screen work against the real API responses. The account exists so that work can
be done against a running system instead of hand-written fixtures, and so the
teammate never needs database credentials to do it.

It is not an operator account, not a data-entry account, and not a support
account. It grants no ability to change users, roles, modules, or the registry.

## 2. Role

`viewer`, and nothing else.

`viewer` is one of the five roles in `AppRole` (`backend/models.py`). Its grants
are defined in `ROLE_PERMISSION_DEFAULTS` (`backend/rbac/registry.py`) as
exactly `MODULE_VIEW_PERMISSION_KEYS` — the `*.view` permission of every
non-admin module. No action permissions, no `admin.*` permissions.

The ten grants, confirmed present in `role_permissions` for `viewer`:

```
check_control.view   cmp_tcm.view       cover_merge.view   crew_hours.view
effectivity.view     mail_merge.view    task_extractor.view
task_stamping.view   tcm_indexing.view  utilization.view
```

The account is created with status `password_change_required`, so the first
login can only reach `POST /api/auth/change-password` until the temporary
password is replaced.

## 3. What the account can reach

Permission checks are enforced server-side; the frontend gates mirror them but
are not the enforcement point.

### Reachable

| Route | Note |
|---|---|
| `POST /api/auth/login`, `/change-password`, `GET /me`, `PUT /profile` | Own account only |
| `GET /api/modules`, `/api/modules/{key}` | Filtered to the ten viewable modules |
| `GET /api/notifications`, `POST /{id}/read`, `POST /read-all` | Own rows only |
| `GET/POST/DELETE /api/uploads`, `GET /api/uploads/{id}/download` | Own rows only |
| `GET /api/jobs`, `/api/jobs/{id}`, `GET /api/downloads/{filename}` | Own rows only |
| `POST /api/jobs` | **Gated by module *view* only — see §4** |
| `GET /api/projects` | Deliberately open to every authenticated user |
| `GET /api/statistics/crew-hours/report` | Needs `crew_hours.view` — held |
| `POST /api/copilot/ask`, `/approve` | Needs `crew_hours.view` — held |

### Refused with 403

| Route | Reason |
|---|---|
| `POST /api/projects` | Requires `engineer`, `admin`, or `super_admin` |
| `DELETE /api/projects/{id}` | Owner or admin only |
| `GET /api/statistics/crew-hours/report/export` | Needs `crew_hours.export` |
| All of `/api/admin/*` | Needs `admin.users.*`, `admin.roles.*`, `admin.modules.manage`, or `admin.audit.view` |
| `POST /api/statistics/crew-hours` | Returns 501; not implemented |

In the SPA, `src/routes/_authenticated/admin/route.tsx` redirects away from
`/admin/*` for anyone without `admin` or `super_admin`, and `projects.tsx`
hides the create button behind the same `engineer+` check the API enforces.

## 4. Known sharp edge: job creation

`POST /api/jobs` (`backend/main.py`) authorizes with `_module_is_visible`,
which tests the module's `required_view_permission`. It does **not** require an
action permission. A `viewer` therefore holds `.view` on all eight modules that
have a worker handler (`task_extractor`, `task_stamping`, `effectivity`,
`check_control`, `utilization`, `cmp_tcm`, `cover_merge`, `mail_merge`) and can
enqueue real processing work on any of them, against files the account itself
uploaded.

This is a write capability, not a read one. It is in scope for whoever approves
this account, and it is the one grant that does not match the plain reading of
"viewer".

## 5. Database credentials are never shared

Frontend work runs against **the API or a local database**. That is the rule,
without exception:

- No teammate receives `DATABASE_URL`, `SQL_SERVER_*` values, or any other
  contents of `.env`.
- No teammate receives a shared database login, read-only or otherwise.
- Design work that needs data uses this API account against a running backend,
  or a local database the teammate provisions themselves (`redsea.db` via
  `alembic upgrade head`) with their own throwaway data.
- If a task appears to require direct database access, that is a signal the API
  is missing an endpoint. Raise it; do not route around it with credentials.

Credential handling generally: temporary passwords are printed once to the
operator's console and are never written to a file, document, commit, log, or
audit row. `record_audit` sanitizes any metadata key containing `password`,
`passwd`, `hash`, `token`, or `secret` (`backend/rbac/permissions.py`), but the
first line of defence is not putting the value there at all.

## 6. Provisioning

Use `POST /api/admin/users` with an `admin.users.manage` token. It is the only
supported creation path for a non-bootstrap account: it generates the temporary
password with `secrets.token_urlsafe(24)`, hashes it through
`get_password_hash`, sets `status = password_change_required`, writes the
`admin_user_creation` and `role_assignment` audit rows, and returns the
temporary password exactly once in the response body.

`backend/tools/bootstrap_admin.py` is not the right tool here — it refuses to
run once a super admin exists, and it only ever creates `super_admin`.

Do not insert `users` or `user_roles` rows by hand; doing so bypasses password
hashing, the status default, and the audit trail.
