# Security Audit — 2026-08-17

Scope: this repository's application code and configuration (defensive review
and remediation only). No secrets are reproduced in this document.

## Threat model

On-prem web app for airline back-office staff. Assets: crew duty data (LEON),
maintenance documents, user credentials, the LEON refresh token. Adversaries:
a hostile or curious authenticated user (the dominant realistic threat), a
network-adjacent attacker if the service is ever exposed, and accidental
credential leakage through logs/artifacts. Attack surfaces: the REST API, file
upload/download, the LEON integration, and repository hygiene.

## Findings and remediation

### P0 — fixed in this audit

| # | Finding | Root cause | Remediation |
|---|---|---|---|
| 1 | **Crew data exposed to any authenticated session.** `GET /api/statistics/crew-hours/report(+/export)` and `POST /api/copilot/ask|approve` required only a valid token — a `guest` with zero grants could read and export LEON crew duty data. | Routes authenticated but never authorized; the RBAC layer existed and was simply not applied. | Gated by `crew_hours.view` (report, Copilot) and `crew_hours.view + crew_hours.export` (export) via `require_permissions()`. Regression tests assert 403 for grant-less users and pass-through for grant holders. Commit `bddcc5a`. |
| 2 | **Stolen sessions survived password resets.** JWTs carried only `sub`; an admin reset or user password change left old tokens valid for up to 7 days. | No revocation signal in the token. | Tokens now embed the `password_changed_at` stamp, checked on every request; change/reset kills all outstanding tokens, and change-password returns a fresh one. Commit `dea3443`. |

### P1 — fixed in this audit

| # | Finding | Remediation |
|---|---|---|
| 3 | Registration accepted **any password** (change-password required 12 chars) | One shared policy (12–72 bytes) on register and change. |
| 4 | **Account enumeration via login timing** — unknown emails skipped bcrypt | Dummy-hash verification equalizes cost. |
| 5 | **Upload storage paths and Python tracebacks sent to clients** — raw ORM rows from `/api/uploads` and `/api/jobs` | Explicit serializers; job `logs` and `input_refs` are no longer part of any response. Commit `c45131d`. |
| 6 | **Wildcard CORS origin accepted alongside credentials** and origins un-trimmed | `resolve_cors_origins()`: trimmed, de-slashed, `*` fatal in production. Commit `fd434e8`. |
| 7 | **Unbounded client-controlled `limit`** on jobs/audit listings | Bounded via `Query(ge=1, le=…)`. |
| 8 | **Login rate-limiter map grew forever** (keyed by attacker-chosen emails) | Expired-window sweep past 10k keys. |
| 9 | **Missing DELETE authorization for projects** (UI offered deletion; no endpoint, no ownership rule) | Owner-or-admin `DELETE /api/projects/{id}`, audited. |
| 10 | **Copilot constructed LEON clients before authentication** and crashed (500) when LEON was unconfigured | Auth resolves first; construction failures map to plain 502/503. |

### Previously fixed (verified still in place)

- Upload path traversal (incl. Windows backslash and %2F vectors), streaming
  size enforcement, magic-byte validation, SHA-256, server-side names — all in
  `backend/storage.py` (commit `cc2a0ac`), covered by `test_secure_uploads.py`.
- Job-submission module authorization + input-file ownership (commit `e78c35a`).
- Secrets untracked from git (commit `5be7448`) — see "Residual risks" below.
- JWT secret required, ≥32 chars, no default.
- Audit metadata sanitizer strips password/hash/token/secret keys.

## Secrets review

- No hardcoded secrets in tracked source (scanned).
- `.env` (with `JWT_SECRET_KEY`, DB credentials, `WORKER_HMAC_SECRET`) and
  `redsea.db` **exist in git history** (removed at `5be7448` but reachable via
  earlier commits). `backend/.env` / `backend/.envpython` on the dev machine
  hold a live LEON refresh token — now git-ignored.
- Tests never rely on live LEON credentials; the LEON env is cleared or the
  service is stubbed in every API test.

## Residual risks (documented, not silently accepted)

1. **History rewrite needed**: any credential that was ever in `.env` in git
   history (notably `WORKER_HMAC_SECRET`, old `JWT_SECRET_KEY`, Supabase keys,
   SQL credentials) must be considered compromised. Rotate them and/or rewrite
   history (`git filter-repo`) before the repo is shared more widely.
2. **Tokens in localStorage** — XSS would exfiltrate them. Mitigated by React's
   escaping and no `dangerouslySetInnerHTML`; a move to httpOnly cookies +
   CSRF token is the strategic fix (tracked in TECHNICAL_DEBT.md).
3. **7-day token lifetime** with no refresh-token rotation; acceptable
   on-prem, revocation now exists via the password stamp.
4. **Rate limiting is process-local**; the persistent account lockout
   (`failed_login_count`) is the real control across workers.
5. **No antivirus scanning of uploads** — `scan_state` is a seam
   (`not_scanned`), deliberately not faked.
6. **In-process job execution** can be DoS'd by heavy OCR jobs; the accepted
   durable-jobs design addresses this and is the next roadmap slice.
