# ADR-024: ARQ worker foundation for health supervision

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder

## Context

ADR-003 selected Redis + ARQ. Phase 8 needs the first real worker without containerizing the API or adding trading jobs.

## Decision

- Add `arq` dependency to the API project (shared domain code).
- Place worker entry under `workers/health_supervisor`.
- Reuse API services/settings/DB/audit (no privilege side door).
- Optional Compose service under profile `workers`; API remains local uvicorn.

## Consequences

- Worker and API share institutional rules.
- Compose stays infrastructure-first; worker is opt-in via profile.
- Future workers should follow the same reuse pattern.
