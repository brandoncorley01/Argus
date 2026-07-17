# ADR-003: Redis and ARQ worker architecture

- Status: Accepted
- Date: 2026-07-15
- Deciders: Founder

## Context

Argus needs a Redis-backed coordination layer for sessions (later), locks, health supervision, and background jobs without introducing Celery complexity in v0.1.

## Decision

- Use **Redis 7** for coordination, caching/locks, and as the broker/backend for workers.
- Use **ARQ** for the initial Redis-backed worker unless a concrete incompatibility is discovered.
- Phase 1 provisions Redis only; worker application code is deferred.
- Worker processes must reuse the same institutional control rules as the API (no privilege side doors).

## Consequences

- Small operational footprint suitable for a private foundation.
- API and worker rule drift is a risk — shared packages should be introduced when workers land.
- ARQ choice may be revisited via a superseding ADR if incompatible.
