# ADR-027: Strategy Laboratory closed research registry

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder
- Superseding notes: Registry expanded 2026-09-04 with regime families (still closed; no user code)

## Context

Phase 11 requires governed research without live capital or broker access.

## Decision

- Strategies are versioned documents with auditable lifecycle.
- Only built-in strategy classes may execute in the research engine:
  - `buy_and_hold`
  - `sma_crossover`
  - `grid_trading` (sideways / quiet ranges)
  - `dca` (interval buys + dip safety orders)
  - `trend_momentum` (RSI + MACD)
  - `cross_venue_arb` (requires verified `secondary_closes`; stays flat otherwise)
- Research results are immutable when completed.
- Walk-forward and validation must separate in-sample vs out-of-sample evidence.
- Optimization workloads require explicit budgets.
- No strategy may call brokers or submit live orders.
- Cross-venue arbitrage research must not invent venue prices; live multi-exchange execution remains forbidden until Founder-approved market-data + micro-live unlocks.

## Consequences

- Arbitrary user code execution is out of scope.
- Paper trading (Phase 12) consumes approved strategy versions via institutional interfaces only.
- Paper detectors may mirror the same families for Alpha Radar observation.
