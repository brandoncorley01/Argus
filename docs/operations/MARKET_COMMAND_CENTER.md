# Market Command Center (Home)

Home (`/today`) is the Founder **Market Command Center**: paper account ops plus
an **observation-only** market scan / decision picture.

Build id: `market-command-v2`.

## Founder readability (v2)

- **What Argus is doing now** strip with a plain-language headline
- **Scan markets now** button (observation-only)
- Opportunity cards show **Why** plus teaching buttons (Looks good / Skip / Need more data / Looks wrong) — audited, never places orders
- Performance section hides empty “Unavailable” clutter
- Status API includes `cycle_id`/`candidate_id` on last decision so Home no longer blanks the scanner while candidates still render

## Paper teaching

`POST /api/v1/market/scan/teach` records Founder preference events (`market.scan.teach` audit). Does not bypass risk or submit orders.

## Data inconsistencies found and corrected

| Issue | Cause | Fix |
| --- | --- | --- |
| Warning with no explanation | Status derived without reason text | Plain-language `statusExplanation` on the status bar |
| Entry looked like committed capital | `money()` prefixed `+` on all positives | `money()` for balances/prices; `moneyPnl()` for P&L only |
| Current price Unavailable / P&L shown as 0 | `unrealized_pnl` never marked; UI treated 0 as real | Marks from latest `market_ohlcv_bars` close; missing mark → P&L **Unavailable** |
| Capital in trades ≠ portfolio exposure | Live committed vs report snapshot mixed | Live exposure always from summary; report exposure labeled separately |
| “Trades completed today” vs empty recent list | Daily `trade_count` = **fill count**, UI showed sell fills without replay | Closed-trade replay endpoint; labels distinguish fill count vs closed trades |
| Activity feed = technical health noise | Ops/audit flood | **Argus Decision Stream** from scan events + fills; technical IDs optional |

## Metric sources

| UI | Source |
| --- | --- |
| Argus status + explanation | `/ready`, pause/kill, health, scanner/marks freshness |
| Scanner status / pipeline / candidates / events | `/api/v1/market/scan/*` |
| Account summary | `/api/v1/paper/portfolios/{id}/summary` |
| Active trades | `/position-summaries` (marks from OHLCV when present) |
| Closed trades | `/closed-trades` (fill replay) |
| Daily report fields | `/api/v1/operations/daily-reports` (may be **yesterday**) |
| Decision stream poll | `/api/founder/decisions` |

## Market scanner (observation only)

- Worker cron every 2 minutes: `run_market_scan_cycle`
- Home may trigger `POST /api/v1/market/scan/run` when no recent cycle
- Evaluates active `market_instruments` against persisted OHLCV using research `sma_crossover`
- **Does not place orders** or bypass risk / pause / kill switch
- Candidates, stages, rejection reason codes persisted with correlation IDs
- Event retention ~7 days; per-cycle event cap

## Still unavailable (honest)

- Full candlestick chart UI (sparkline of verified closes when bars exist)
- Stop/take-profit on paper books
- Daily risk remaining, consecutive losses, drawdown series
- Auto-execution from candidates into paper orders
- Exit reason on closed trades (not stored on fills)

## Safety

- Paper vs Live labels preserved; no Live unlock on Home
- Scanner failure never blocks the trading engine
- Pause / kill / audit behavior unchanged
