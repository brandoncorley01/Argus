# ADR-026: Market Intelligence observation boundary

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder

## Context

Phase 10 introduces institutional market observation. Trading, signals, and execution must remain forbidden.

## Decision

- Market Intelligence is an **observation department**: ingest, normalize, store, monitor quality.
- Multi-provider registry with priority-based failover metadata and health probing.
- Manual intake is first-class; null probe never emits market payloads; HTTP adapters require explicit config.
- No strategy, order, position, or signal tables in this phase.
- ROADMAP Phase 10 is Market Intelligence; Hardening & CI moves to Phase 11.

## Consequences

- Feature `feat.market.intelligence` may activate for observation APIs only.
- Live exchange credentials and execution remain locked per `AGENTS.md`.
