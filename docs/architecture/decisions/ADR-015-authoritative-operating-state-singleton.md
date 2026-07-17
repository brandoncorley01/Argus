# ADR-015: Authoritative operating-state singleton

- Status: Accepted
- Date: 2026-07-17
- Deciders: Founder (Phase 7 defaults D4)

## Context

Phase 3 introduced `system_states` (singleton) and `operating_mode_history`. Phase 7 must add versioning, emergency flags, and policy references without creating a second source of truth.

## Decision

Extend the existing `SystemState` singleton (`singleton_key='current'`) as the sole authoritative current mode. History remains append-only evidence. No cache or secondary table may independently assert current mode.

### Initialization concurrency (Phase 7 remediation)

Singleton creation uses a PostgreSQL transaction-scoped advisory lock:

`SELECT pg_advisory_xact_lock(hashtext('argus.operating_mode.singleton'))`

Callers serialize on initialize. After the lock, the service reloads SystemState; if present it returns without writing. Otherwise it creates exactly one history row, one SystemState row, and one `operating_mode.initialized` audit in a fail-closed commit. Residual unique violations reload the winner and never surface raw `IntegrityError` to API clients.

## Consequences

- Migrations evolve columns in place.
- Missing singleton during normal operation fails closed (`institutional_state_missing`).
- Initialization creates OFF once and is idempotent thereafter, including under concurrent Founder callers.
