# ADR-021: Append-only heartbeats with ordering and idempotency

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder

## Context

High-frequency probe samples must not become the institutional record. Concurrent workers must not corrupt health evidence.

## Decision

Store heartbeat evidence in append-only `health_heartbeats` with:

- per-service monotonic `sequence_number`
- idempotency keys + fingerprints
- immutability trigger (no UPDATE/DELETE)
- current status projected into `service_health_projections`

Meaningful status changes also emit `service_health_events`.

## Consequences

- Replay is safe; stale sequences fail closed.
- Storage grows with heartbeats (acceptable for v0.1 foundation cadence).
- Projections are derived state and may be recomputed from evidence.
