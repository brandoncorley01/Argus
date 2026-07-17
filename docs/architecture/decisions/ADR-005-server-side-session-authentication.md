# ADR-005: Server-side session authentication

- Status: Accepted
- Date: 2026-07-15
- Deciders: Founder

## Context

v0.1 is a private institutional system with roles `FOUNDER`, `OPERATOR`, and `VIEWER`. Token-centric JWT auth adds complexity (refresh rotation, client storage risks) without clear benefit for this stage.

## Decision

Use **secure server-side sessions** with **HTTP-only cookies** for v0.1 authentication.

- Do not use JWT as the primary v0.1 session mechanism.
- Cookies must be marked Secure (in non-local HTTPS deployments), HttpOnly, and SameSite-appropriate.
- Session creation, destruction, and failures must be auditable once the audit framework exists.
- Implementation is deferred until the auth phase; this ADR locks the direction.

## Consequences

- Simpler revocation (server-side invalidate).
- Requires CSRF protections for cookie-based mutating requests.
- Redis or Postgres may back session storage — choose at implementation time without changing this ADR’s cookie/session stance.
