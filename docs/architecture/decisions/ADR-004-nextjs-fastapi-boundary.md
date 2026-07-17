# ADR-004: Next.js and FastAPI technology boundary

- Status: Accepted
- Date: 2026-07-15
- Deciders: Founder

## Context

Argus requires a clear separation between operator-facing UI and institutional backend controls. Mixing data-store access into the frontend would weaken auditability and responsibility boundaries.

## Decision

- **Frontend:** Next.js App Router with TypeScript — product name for the operator UI phase: **Executive Operations Center** (not a decorative dashboard).
- **Backend:** Python 3.12+, FastAPI, SQLAlchemy 2.x, Pydantic, Alembic.
- **Package managers:** pnpm (JavaScript), uv (Python).
- Frontend must not connect directly to PostgreSQL or Redis; all institutional mutations go through the API.
- Do not scaffold Next.js or FastAPI in Phase 0/1.

## Consequences

- Clear security and audit boundary at the HTTP API.
- Contract discipline (OpenAPI) becomes important once both apps exist.
- Monorepo must host both runtimes without premature coupling.
