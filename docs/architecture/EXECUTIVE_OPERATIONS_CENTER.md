# Executive Operations Center (Phase 9)

## Purpose

The Executive Operations Center (EOC) is the institutional command center for Argus. It presents **real control-plane state** to Founder, Operator, and Viewer roles. It does not invent metrics, unlock locked modes, or replace API authorization.

## Boundary (ADR-004)

| Layer | Responsibility |
| --- | --- |
| `apps/eoc` (Next.js App Router) | Presentation, session cookie bridging, confirmation UX |
| `apps/api` (FastAPI) | AuthN/AuthZ, audit, mutations, institutional truth |

Frontend must not connect to PostgreSQL or Redis.

## Authentication bridge

1. Login posts to FastAPI `/api/v1/auth/login` from a Next.js Server Action.
2. Session cookie `argus_session` is stored HttpOnly on the EOC origin.
3. CSRF token from the login body is stored as HttpOnly `argus_csrf` and sent as `X-CSRF-Token` on mutating API calls.
4. RSC and Server Actions call FastAPI with forwarded cookies (`ARGUS_API_BASE_URL`).

UI role checks only hide controls. The API remains authoritative.

## Screens

| Route | Purpose |
| --- | --- |
| `/login` | Authentication |
| `/overview` | Role-aware Founder / Operator / Viewer dashboard |
| `/operations` | Operating mode, availability, transitions, emergency |
| `/services` | Process health/ready, registry projections, lease, protective actions |
| `/workers` | Worker identities and instances |
| `/incidents` | Incident list + create; detail + lifecycle |
| `/audit` | Audit explorer + event detail |
| `/configurations` | Configuration documents and versions |
| `/policies` | Policy documents and versions |
| `/administration` | Founder user creation |

## Empty / degraded states

When the API is unreachable or returns empty collections, the EOC shows explicit empty, unavailable, or error states—never fabricated zeros presented as institutional health.

## Local run

See `apps/eoc/README.md`.

## Out of scope (Phase 9)

Market data, trading, strategies, execution, treasury.
