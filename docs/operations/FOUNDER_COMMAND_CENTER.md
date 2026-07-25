# Founder Command Center (Home)

Home (`/today`) is the Founder daily command center for **paper** practice.
Build id: `trading-cockpit-v1`.

See [`TRADING_COCKPIT.md`](./TRADING_COCKPIT.md),
[`MARKET_COMMAND_CENTER.md`](./MARKET_COMMAND_CENTER.md), and
[`PAPER_TRAINING_LAB.md`](./PAPER_TRAINING_LAB.md).

Primary navigation: **Home · Paper Training · Trades · Reports · Settings**.
Diagnostics live under **Advanced**.

## Controls

| Control | Behavior |
| --- | --- |
| **Start Argus** | Control-center start (self-updates from GitHub `main`, syncs code, starts infra/API/worker). Browser Start keeps the dashboard process up and soft-refreshes Home. |
| **Stop Argus** | Existing control-center stop (keeps dashboard available). Remains clickable while Start is busy. |
| **Pause New Trades** | Blocks **new entries**; risk-reducing **sells** on open longs remain allowed. Audited as `paper.pause_new_entries`. |
| **Refresh recent prices** | Downloads public market candles into Recent Price History (never invents prices). |
| **Scan markets now** | Runs a market scan; Automatic Practice may open paper trades after risk checks. |

Live unlock is **not** offered on Home. Live Readiness on Paper Training never unlocks Live.

## Data sources

| Section | Source |
| --- | --- |
| What Argus is doing | `/api/v1/market/scan/status` (plain-language headline) |
| Paper account | `/api/v1/paper/portfolios/{id}/summary` |
| Considering / open trades | scan candidates + position-summaries |
| Timeline | scan events + paper fills |
| Scorecard / coaching | `/api/v1/paper/training/*` |

## Safety

- Paper vs Live labels are explicit.
- Dashboard failure does not affect the trading engine.
- Founder feedback does not change live parameters.
- Missing marks → P&L unavailable (not zero).
