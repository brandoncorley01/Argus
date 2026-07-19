# ADR-020: Governed service registry for health supervision

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder

## Context

Health supervision needs a durable catalog of institutional dependencies and workers without inventing trading or market capabilities.

## Decision

Persist a governed `registered_services` registry (and related worker identities/instances) in PostgreSQL. Seed critical foundation services in the Phase 8 migration. Runtime health evidence references registry rows by foreign key.

## Consequences

- Health evaluation is explicit and auditable.
- New services require migration/governance, not ad-hoc string probes alone.
- Registry mutations remain rare and versioned via migrations in v0.1.
