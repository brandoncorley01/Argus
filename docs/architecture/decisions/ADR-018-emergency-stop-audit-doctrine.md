# ADR-018: Emergency-stop audit fail-closed doctrine

- Status: Accepted
- Date: 2026-07-17
- Deciders: Founder (Phase 7)

## Context

Emergency stop must be independently reliable, but Argus also requires fail-closed audit for critical mutations (ADR-006).

## Decision

`EMERGENCY_STOP` entry and recovery remain fail-closed on audit persistence failure. There is no silent bypass, no unauthenticated kill switch, and no unaudited automatic exit.

**Safety tradeoff:** during an audit outage, emergency entry is refused. Institutional evidence integrity is prioritized over mode-change availability. Operators must restore audit persistence, then retry.

## Consequences

- Emergency still bypasses ordinary capability/policy prerequisites.
- Emergency does **not** bypass authentication, authorization, transactions, or audit.
- Documented recovery procedures cover audit-outage handling.
