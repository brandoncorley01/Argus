# ADR-022: Durable health supervisor lease in PostgreSQL

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder

## Context

Multiple ARQ worker processes may start. Health evaluation and protective actions must not race.

## Decision

Coordinate the supervisor with a PostgreSQL singleton lease (`health_supervisor_leases`) locked via `SELECT … FOR UPDATE`. Redis remains the ARQ broker only. Lease expiry allows failover.

## Consequences

- Lease authority survives Redis flushes.
- Concurrent non-holders observe `lease_held` and skip mutation.
- Requires Postgres availability for supervision (aligned with fail-closed posture).
