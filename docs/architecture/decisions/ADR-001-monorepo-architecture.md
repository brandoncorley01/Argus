# ADR-001: Monorepo architecture

- Status: Accepted
- Date: 2026-07-15
- Deciders: Founder

## Context

Argus needs strict separation of responsibilities across API, Executive Operations Center, workers, shared libraries, infrastructure, and documentation, while remaining a single private institutional codebase.

## Decision

Use a monorepo with top-level anchors:

- `apps/` — application runtimes
- `workers/` — background workers
- `packages/` — shared libraries
- `infrastructure/` — infrastructure documentation and related assets
- `scripts/` — operator scripts
- `tests/` — automated tests
- `docs/` — durable institutional documentation

Do not create empty department folders or fake feature scaffolds. Populate directories when they add real value.

## Consequences

- Single review surface for institutional controls and ADRs.
- Clear boundaries reduce accidental coupling between UI and data stores.
- Tooling (uv, pnpm, Compose) must be coordinated at repo root.
