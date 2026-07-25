# Paper Training Lab

Build id: `paper-training-lab-v1`.

Argus Paper Training is a safe interactive practice environment. It uses the
same decision and risk pipeline intended for Live, with execution routed only
to the simulated paper broker. **Live trading is never unlocked by this lab.**

## Primary navigation

| Nav item | Purpose |
| --- | --- |
| Home | Daily command center (five plain-language questions) |
| Paper Training | Automatic Practice / Coaching Mode, lessons, feedback, scorecard |
| Trades | Open + closed paper trades |
| Reports | Saved reports |
| Settings | Operator settings |
| Advanced | Diagnostics, audit, workers, market data internals, policies |

## Root causes repaired in the market → paper loop

| Break | Cause | Repair |
| --- | --- | --- |
| Scanner status / insufficient history | No instruments and no continuous OHLCV intake | `POST /api/v1/market/prices/refresh` registers default markets and downloads public Coinbase Exchange 15m candles into Recent Price History |
| Single-symbol / empty scan | Instruments never seeded | Refresh ensures an 18-market default universe |
| Wrong rejection label | `< MIN_BARS` coded as `confirmation_incomplete` | Now `insufficient_history` with plain-language copy |
| Scan never entered paper | Observation-only by design | Automatic Practice + Coaching Take call `submit_order` (paper only); worker may auto-enter when mode=`automatic` |
| Stale prices | No scheduled refresh | Worker cron every ~15 minutes refreshes public candles |

Argus still **does not invent** prices or scanner movement. If the public feed
is unreachable, the UI states the precise next step.

## Modes

### Automatic Practice

Argus may open simulated trades from clear Watching candidates after a scan,
still subject to risk limits, pause-new-entries, and kill switch.

### Coaching Mode (default)

Founder must Take or Skip before a paper entry. Coaching is paper-only and is
never an approval dependency for Live.

## Founder feedback

Stored in `paper_trade_feedback` with audit `paper.training.feedback`.
Feedback never changes live parameters. Improvement path remains:

Feedback → paper analysis → suggested adjustment → backtest → paper validation
→ Founder review → versioned policy approval → eligible for Live review.

## Live Readiness (scorecard)

Statuses: Not Enough Evidence → Early Testing → Needs Improvement →
Consistent in Paper → Eligible for Formal Live Review.

**Eligible for Formal Live Review does not unlock Live.** Existing micro-live
authorization remains required.

## Key APIs

| Endpoint | Role |
| --- | --- |
| `POST /api/v1/market/prices/refresh` | Download Recent Price History |
| `GET /api/v1/market/scan/status` | Plain-language Argus status |
| `GET/PUT /api/v1/paper/training/{id}/settings` | automatic \| coaching |
| `POST .../coaching/take\|skip` | Coaching actions |
| `POST .../feedback` | Founder feedback |
| `GET .../scorecard` | Scorecard + Live Readiness |
| `GET /api/v1/paper/training/candidates` | Plain-language candidates + lessons |

## Terminology

| Old | Founder-facing |
| --- | --- |
| persisted OHLCV bars | Recent Price History |
| fill replay closed trades | Closed Trades |
| report fill count | Order Updates |
| report exposure snapshot | Latest Saved Report / Money Currently in Trades |
| worker scan cron | Scheduled Market Scan |
| policy configuration | Trade Rules (in Advanced) |
| reason codes | Why Argus Decided |
