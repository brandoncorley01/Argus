# Advanced Paper Learning Engine

Build id: `live-monitor-v2.13`.

Extends Argus trading intelligence into a **20-day PAPER learning cycle**.
It reuses Opportunity Radar (scan candidates), post-trade reviews, missed
opportunities, paper fills (fees/slippage), and existing risk controls.

## Principles

- Profit is the mission; risk discipline protects the mission; learning improves it.
- PAPER and LIVE stay strictly separated.
- Adaptive strategy confidence is PAPER-only, bounded (−15..+15), auditable,
  reversible, and never applied to live trading.
- High relative volume raises **analysis priority** only — volume alone never
  triggers a trade.
- Day-20 Readiness Report never enables live trading.

## Surfaces

- Paper Training → **Advanced Learning** pane
- `GET /api/v1/paper/training/{portfolio_id}/advanced-learning`
- `GET /api/v1/operations/trading-intelligence/advanced-learning`
- `GET /api/v1/operations/trading-intelligence/advanced-learning/readiness-report`
- `POST /api/v1/operations/trading-intelligence/advanced-learning/evaluate`

## Persistence

- `paper_learning_programs` — 20-day cycle per portfolio
- `paper_learning_day_snapshots` — daily evidence rollups
- `paper_learning_milestones` — milestone checklist with stored evidence
- `paper_strategy_confidence_states` — PAPER adaptive deltas
- `paper_learning_readiness_reports` — immutable hashed Day-20 report

## Worker

After each market scan automation pass, `AdvancedLearningService.evaluate_cycle`
updates snapshots, adaptive confidence, milestones, and (when eligible) the
readiness report.

## Existing certification

The informational 30-day `certification_progress` gate remains unchanged.
Advanced Learning is the Founder-facing 20-day program and readiness report.
