# ADR-027: Strategy Laboratory closed research registry

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder

## Context

Phase 11 requires governed research without live capital or broker access.

## Decision

- Strategies are versioned documents with auditable lifecycle.
- Only built-in strategy classes may execute in the research engine (`buy_and_hold`, `sma_crossover`).
- Research results are immutable when completed.
- Walk-forward and validation must separate in-sample vs out-of-sample evidence.
- Optimization workloads require explicit budgets.
- No strategy may call brokers or submit live orders.

## Consequences

- Arbitrary user code execution is out of scope.
- Paper trading (Phase 12) consumes approved strategy versions via institutional interfaces only.
