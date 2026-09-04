# Strategy Laboratory (Phase 11)

Governed quantitative research department. Strategies are versioned institutional assets. Research runs are reproducible and auditable. **No live execution.**

## Capabilities

- Strategy registry + immutable versions after submit
- Lifecycle: draft → under_review → approved | rejected; suspended / retired / archived
- Deterministic engines: backtest, walk-forward (IS/OOS), bounded optimization, Monte Carlo, sensitivity
- Built-in classes only (closed registry — no broker access):
  - `buy_and_hold`
  - `sma_crossover`
  - `grid_trading` — sideways / quiet range grids
  - `dca` — dollar-cost averaging with dip safety orders
  - `trend_momentum` — RSI + MACD trend/momentum
  - `cross_venue_arb` — research-only spread vs verified `secondary_closes` (flat without them)
- Dataset provenance + content hashes
- Validation reports and strategy comparisons under shared assumptions
- Regime×strategy fit catalog via `GET /api/v1/strategies/registry`
- EOC `/strategies` surfaces real API evidence

## Regime guidance (research / paper)

| Regime | Prefer |
| --- | --- |
| quiet | `grid_trading`, range mean-reversion detectors |
| volatile / trend_down dips | `dca`, dip detectors |
| trend_up / strong direction | `trend_momentum`, SMA / breakout / momentum detectors |
| verified multi-venue discount | `cross_venue_arb` (never invents spreads) |

## Safeguards

- Look-ahead protected (signals use current/past bars only)
- Completed `research_run_results` are DB-immutable
- Optimization budgets are mandatory and bounded
- Reproducible seeds; cancel flag for long runs
- Cross-venue arb does not fabricate secondary venue prices
- Live trading remains disabled

See ADR-027 and `docs/operations/STRATEGY_LABORATORY_RECOVERY.md`.
