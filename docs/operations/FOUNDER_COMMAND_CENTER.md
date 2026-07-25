# Founder Command Center (Home)

Home (`/today`) is the Founder **Market Command Center** for **paper** trading
plus observation-only market scanning.

See also [`MARKET_COMMAND_CENTER.md`](./MARKET_COMMAND_CENTER.md) for scanner
APIs, metric corrections, and unavailable capabilities.

## Controls

| Control | Behavior |
| --- | --- |
| **Start Argus** | Control-center start (self-updates script from GitHub `main`, syncs code, starts infra/API/worker). Browser Start keeps the dashboard process up and soft-refreshes Home. |
| **Stop Argus** | Existing control-center stop (keeps dashboard available for browser control). Remains clickable while Start is busy. |
| **Pause New Trades** | Sets `paper_portfolios.pause_new_entries_active`. Blocks **new entries**; risk-reducing **sells** on open longs remain allowed. Audited as `paper.pause_new_entries`. |

Live unlock is **not** offered on Home. Live remains behind existing micro-live authorization.

## Data sources

| Section | Source |
| --- | --- |
| System / heartbeat | `/ready`, `/api/v1/operations/system-health`, `/api/v1/paper/providers` |
| Trading mode | `/api/v1/micro-live/status` (Paper when live locked) |
| Account summary | `GET /api/v1/paper/portfolios/{id}/summary` |
| Active trades | `GET /api/v1/paper/portfolios/{id}/position-summaries` |
| Activity feed | Audit events + operational events + paper fills (`/api/founder/activity` polls ~15s) |
| Performance | `/api/v1/operations/daily-reports` (only fields the report actually stores) |
| Recent exits | Recent **sell** fills (entry/P&amp;L/reason shown Unavailable when not stored) |

## Unavailable by design (not fabricated)

- Live broker marks / stop-loss / take-profit on paper positions (null → UI “Unavailable”)
- Equity curve chart (no verified time series)
- Remaining daily risk allowance, consecutive losses, drawdown (not in daily report)
- Average win/loss (not stored; UI shows largest winner/loser when present, else Unavailable)

## Safety

- Paper vs Live labels are explicit on Home.
- Pause does not bypass kill switch; kill switch still blocks all submits.
- Dashboard render failures must not change trading engine behavior; Home only reads APIs and issues audited control actions.
