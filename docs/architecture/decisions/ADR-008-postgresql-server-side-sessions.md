# ADR-008: PostgreSQL-backed server-side sessions

- Status: Accepted
- Date: 2026-07-16
- Deciders: Founder (Phase 5 implementation defaults)

## Context

ADR-005 requires HTTP-only cookie sessions without JWT, and allows Redis or Postgres as the session store. Phase 5 must support revocation, expiration audit events, CSRF synchronizer tokens, and fail-closed audit integration.

## Decision

1. Store sessions in **PostgreSQL** (`auth_sessions`), not Redis, for v0.1.
2. Persist only **SHA-256 hashes** of session and CSRF tokens; cookies carry opaque secrets.
3. Use absolute session TTL (default 8 hours), configurable via settings.
4. Track login attempts in PostgreSQL (`login_attempts`) for lockout controls.
5. Require `X-CSRF-Token` on mutating authenticated requests.
6. Bootstrap the first Founder only through an explicit env-driven CLI process.

## Consequences

- Session revocation and auditability align with the system-of-record posture (ADR-002).
- Redis remains available for future worker/lock use without becoming the auth source of truth.
- Operators must run migrations before authentication works.
