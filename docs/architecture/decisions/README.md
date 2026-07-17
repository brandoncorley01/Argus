# Architecture Decision Records

ADRs capture major technical decisions for Argus. Every major technical decision must receive an ADR in this directory.

## Index

| ADR | Title | Status |
| --- | --- | --- |
| [ADR-001](ADR-001-monorepo-architecture.md) | Monorepo architecture | Accepted |
| [ADR-002](ADR-002-postgresql-system-of-record.md) | PostgreSQL as institutional system of record | Accepted |
| [ADR-003](ADR-003-redis-arq-worker-architecture.md) | Redis and ARQ worker architecture | Accepted |
| [ADR-004](ADR-004-nextjs-fastapi-boundary.md) | Next.js and FastAPI technology boundary | Accepted |
| [ADR-005](ADR-005-server-side-session-authentication.md) | Server-side session authentication | Accepted |
| [ADR-006](ADR-006-fail-closed-audit-policy.md) | Fail-closed audit policy | Accepted |
| [ADR-007](ADR-007-foundational-institutional-database-modeling.md) | Foundational institutional database modeling | Accepted |
| [ADR-008](ADR-008-postgresql-server-side-sessions.md) | PostgreSQL-backed server-side sessions | Accepted |
| [ADR-009](ADR-009-config-policy-version-lifecycle.md) | Configuration and policy version lifecycle | Accepted |
| [ADR-010](ADR-010-canonical-payload-hashing.md) | Canonical JSON payload hashing | Accepted |
| [ADR-011](ADR-011-atomic-version-activation.md) | Atomic configuration and policy activation | Accepted |
| [ADR-012](ADR-012-secret-detection-version-payloads.md) | Secret detection for versioned payloads | Accepted |
| [ADR-013](ADR-013-database-immutability-triggers.md) | Database-enforced version immutability triggers | Accepted |
| [ADR-014](ADR-014-institutional-identity-projection-and-retirement.md) | Institutional Identity projection and retirement | Accepted |

## ADR template

```markdown
# ADR-NNN: Title

- Status: Proposed | Accepted | Superseded | Deprecated
- Date: YYYY-MM-DD
- Deciders: Founder

## Context
## Decision
## Consequences
```
