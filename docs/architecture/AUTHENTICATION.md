# Authentication architecture (Phase 5)

## Overview

Argus uses **local username/email + password** authentication with **Argon2id** password hashes and **server-side PostgreSQL sessions** delivered via **HTTP-only cookies**. JWT and OAuth are out of scope for v0.1.

See ADR-005 and ADR-008.

## Roles

| Role | Access |
| --- | --- |
| `FOUNDER` | Full authority including user creation and role assignment |
| `OPERATOR` | Operational read/write for future ops APIs; **cannot** perform Founder-only governance (user create / role assign) |
| `VIEWER` | Read-only; mutating routes denied |

Deny by default: missing authentication → 401; missing role → 403 (audited as `authz.denied`).

## Session security

| Property | Behavior |
| --- | --- |
| Cookie name | `argus_session` (configurable) |
| Cookie flags | `HttpOnly`; `Secure` via `SESSION_COOKIE_SECURE`; `SameSite` via `SESSION_COOKIE_SAMESITE` (default `lax`) |
| Server storage | `auth_sessions.token_hash` / `csrf_token_hash` only |
| TTL | Absolute; default 8 hours (`SESSION_TTL_HOURS`) |
| Logout | Sets `revoked_at`; cookie cleared |
| Expiration | Lazy revoke on resolve; audits `auth.session.expired` |

## CSRF

Mutating authenticated requests must send header `X-CSRF-Token` matching the token returned at login. GET/HEAD/OPTIONS do not require CSRF.

## Lockout

After `LOGIN_MAX_FAILURES` (default 5) failed attempts for the same identifier+IP within `LOGIN_FAILURE_WINDOW_MINUTES` (default 15), further logins fail closed for `LOGIN_LOCKOUT_MINUTES` (default 15). Failures and lockouts are audited without revealing whether the user exists. Client message is always `Invalid credentials`.

## Endpoints

| Method | Path | Auth |
| --- | --- | --- |
| POST | `/api/v1/auth/login` | Public |
| POST | `/api/v1/auth/logout` | Session + CSRF |
| GET | `/api/v1/auth/me` | Session |
| POST | `/api/v1/auth/users` | Founder + CSRF |
| POST | `/api/v1/auth/users/{id}/roles` | Founder + CSRF |
| GET | `/api/v1/audit/events` | Any authenticated role |

## Founder bootstrap

Never hardcode credentials. From `apps/api`:

```powershell
$env:ARGUS_BOOTSTRAP_USERNAME = "founder"
$env:ARGUS_BOOTSTRAP_PASSWORD = "your-long-passphrase"
$env:ARGUS_BOOTSTRAP_EMAIL = "founder@example.com"  # optional
python -m uv run python -m app.bootstrap_founder
Remove-Item Env:ARGUS_BOOTSTRAP_PASSWORD
```

Rules:

- Fails if a Founder already exists unless `ALLOW_ADDITIONAL_FOUNDERS=true`
- Password must be at least 12 characters
- Audits `auth.founder.bootstrap` and `auth.founder.create`

## Recovery if Founder access is lost

1. Keep database backups; do not delete `users` / `auth_sessions` casually.
2. If the Founder password is lost but DB access remains, an emergency break-glass requires offline Founder-approved procedure: set a new Argon2id hash via a controlled maintenance script (not shipped as a default open endpoint).
3. Prefer restoring from backup over granting additional Founders.
4. Additional Founders remain disabled by default (`ALLOW_ADDITIONAL_FOUNDERS=false`).

Until a dedicated break-glass tool is approved, treat lost Founder credentials as an incident: stop mutating systems, restore from a known-good backup, and rotate secrets.

## Audit events (auth)

- `auth.login.success`
- `auth.login.failure`
- `auth.login.lockout`
- `auth.logout`
- `auth.session.expired`
- `auth.csrf.rejected`
- `authz.denied`
- `auth.user.create`
- `auth.role.assign`
- `auth.founder.bootstrap`
- `auth.founder.create`
