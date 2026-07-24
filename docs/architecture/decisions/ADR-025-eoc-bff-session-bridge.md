# ADR-025: Executive Operations Center BFF session bridge

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder

## Context

Phase 9 introduces the Next.js Executive Operations Center. The API uses HttpOnly session cookies and CSRF tokens designed for same-site browser clients. Cross-origin browser→API calls would require CORS and cookie policy changes that weaken the Phase 5 security model.

## Decision

- EOC uses a **server-side BFF pattern**: React Server Components and Server Actions call FastAPI from the Next.js server.
- Session cookie is re-issued on the EOC origin after login; CSRF is stored in a companion HttpOnly cookie and injected as `X-CSRF-Token`.
- No direct browser→Postgres/Redis access (ADR-004).
- Frontend RBAC is presentation-only.

## Consequences

- Operators run API (`:8000`) and EOC (`:3000`) locally; configure `ARGUS_API_BASE_URL`.
- OpenAPI remains the contract; EOC typed client mirrors schemas without inventing fields.
- Future same-origin reverse-proxy deployment can collapse origins without changing authorization semantics.
