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
| [ADR-015](ADR-015-authoritative-operating-state-singleton.md) | Authoritative operating-state singleton | Accepted |
| [ADR-016](ADR-016-transition-locking-and-state-versioning.md) | Transition locking and state versioning | Accepted |
| [ADR-017](ADR-017-durable-operating-mode-idempotency.md) | Durable operating-mode idempotency | Accepted |
| [ADR-018](ADR-018-emergency-stop-audit-doctrine.md) | Emergency-stop audit fail-closed doctrine | Accepted |
| [ADR-019](ADR-019-mode-availability-and-prerequisites.md) | Mode availability and prerequisite honesty | Accepted |
| [ADR-020](ADR-020-governed-service-registry.md) | Governed service registry for health supervision | Accepted |
| [ADR-021](ADR-021-append-only-heartbeats.md) | Append-only heartbeats with ordering and idempotency | Accepted |
| [ADR-022](ADR-022-durable-supervisor-lease.md) | Durable health supervisor lease in PostgreSQL | Accepted |
| [ADR-023](ADR-023-system-actor-safe-mode.md) | SYSTEM actor auto-degrade to SAFE_MODE | Accepted |
| [ADR-024](ADR-024-arq-health-worker-foundation.md) | ARQ worker foundation for health supervision | Accepted |
| [ADR-025](ADR-025-eoc-bff-session-bridge.md) | Executive Operations Center BFF session bridge | Accepted |
| [ADR-026](ADR-026-market-intelligence-observation-boundary.md) | Market Intelligence observation boundary | Accepted |
| [ADR-027](ADR-027-strategy-laboratory-closed-registry.md) | Strategy Laboratory closed research registry | Accepted |
| [ADR-028](ADR-028-execution-gateway-paper-provider.md) | Execution Gateway and Internal Paper Provider | Accepted |
| [ADR-029](ADR-029-micro-live-deny-by-default.md) | Micro-Live Institution deny-by-default architecture | Accepted |
| [ADR-030](ADR-030-treasury-simulated-ledger-boundary.md) | Treasury simulated-ledger boundary | Accepted |

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
