# ADR-007: Foundational institutional database modeling

- Status: Accepted
- Date: 2026-07-16
- Deciders: Founder (Phase 3 implementation)

## Context

Argus v0.1 Foundation requires a durable PostgreSQL schema for institutional control-plane entities before authentication APIs, mode services, or trading domains exist. Modeling choices must support auditability, versioned configuration/policy, explicit operating modes, feature locks, and maturity tracking without inventing execution or market tables.

## Decision

1. Use SQLAlchemy 2.x declarative mapping with UUID primary keys and timezone-aware UTC timestamps (`DateTime(timezone=True)` with database `now()` defaults).
2. Persist approved operating-mode names and RBAC roles as PostgreSQL native enums (`OFF`, `OBSERVE`, `PAPER`, `MICRO_LIVE`, `NORMAL_LIVE`, `SAFE_MODE`, `EMERGENCY_STOP`; `FOUNDER`, `OPERATOR`, `VIEWER`).
3. Represent configuration and policy as immutable version rows under documents, with partial unique indexes enforcing at most one active version per document.
4. Use JSONB only for version document content, audit payloads, and feature dependency lists — not as a substitute for relational identity/mode/role columns.
5. Enforce institutional integrity in the database where practical:
   - locked features require non-empty `lock_reason`
   - capability levels constrained to 0–6
   - closed incidents require `closed_at`
   - `system_states.singleton_key` uniqueness for current mode singleton
6. Manage schema exclusively via Alembic; downgrade must drop native enum types so upgrade-from-empty remains repeatable.
7. Do not create trading, market-data, strategy, execution, or treasury-calculation tables in this revision.

## Consequences

- Control-plane schema is available for later audit/auth/mode services without premature trading surface area.
- Enum and partial-index discipline improves safety but requires careful migration downgrade handling on PostgreSQL.
- `password_hash` exists on `users` for future session auth; no authentication API is implemented in Phase 3.
