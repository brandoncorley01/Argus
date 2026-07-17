# ADR-002: PostgreSQL as institutional system of record

- Status: Accepted
- Date: 2026-07-15
- Deciders: Founder

## Context

Argus requires an auditable, durable system of record for identity, configuration/policy versions, audit events, operating mode, and later domain data. Fabricated or ephemeral stores are unacceptable for institutional mutations.

## Decision

Use **PostgreSQL 16** as the institutional system of record.

- Schema changes will use **SQLAlchemy 2.x** models and **Alembic** migrations (introduced after Phase 1).
- Phase 1 provides only the database service via Docker Compose — no application schemas yet.
- Redis is not the system of record.

## Consequences

- Strong transactional integrity for fail-closed audit and mode transitions.
- Operational dependency on Postgres availability for readiness.
- Migration discipline is mandatory; no undocumented production DDL.
