# Strategy Laboratory (Phase 11)

Governed quantitative research department. Strategies are versioned institutional assets. Research runs are reproducible and auditable. **No live execution.**

## Capabilities

- Strategy registry + immutable versions after submit
- Lifecycle: draft → under_review → approved | rejected; suspended / retired / archived
- Deterministic engines: backtest, walk-forward (IS/OOS), bounded optimization, Monte Carlo, sensitivity
- Built-in classes only: `buy_and_hold`, `sma_crossover` (closed registry — no broker access)
- Dataset provenance + content hashes
- Validation reports and strategy comparisons under shared assumptions
- EOC `/strategies` surfaces real API evidence

## APIs

Prefix: `/api/v1/strategies`

## Safeguards

- Look-ahead protected (signals use current/past bars only)
- Completed `research_run_results` are DB-immutable
- Optimization budgets are mandatory and bounded
- Reproducible seeds; cancel flag for long runs

See ADR-027 and `docs/operations/STRATEGY_LABORATORY_RECOVERY.md`.
