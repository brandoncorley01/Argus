# Live Trading Cockpit

Build id: `trading-cockpit-v1.2`.

Home presents a visual **Trading Cockpit** driven only by verified market data,
scan cycles, candidates, and paper portfolio figures. Motion reflects real
value changes — Argus does not invent prices or pretend to scan.

## Crash recovery (v1.1+)

- Cockpit timestamps/prices are JSON-safe (ISO strings / decimal strings)
- Missing Paper Training tables no longer 500 the cockpit endpoint — Home gets
  a degraded empty cockpit and keeps rendering
- `scripts/migrate-up.ps1` (Start Argus) calls `repair_training_schema.py` to
  verify `paper_training_settings` and re-apply the training migration if
  alembic was stamped without tables
- Home shows a friendly recovery panel instead of a blank Internal Server Error

## Hydration (v1.2)

- Live countdowns start from server snapshot seconds, then tick after mount
  (no `Date.now()` during SSR)
- Timestamps render as deterministic UTC strings to avoid locale SSR/client mismatch

## Continuous scanning

- Scan interval: **1 minute** (`SCAN_INTERVAL` + worker cron every minute)
- Price refresh remains on its own schedule (~15 minutes)
- Home may trigger a scan when the last cycle is ≥ 1 minute old

## Cockpit API

`GET /api/v1/market/scan/cockpit` returns:

- Gauges: markets monitored, current market, scan progress, next scan,
  possible trades, watching / awaiting confirmation, open trades, risk used
- **Market wall** tiles with sparkline closes, outlook, status, last analyzed
- **Watch plans** with server timestamps: watching_since, expire_at (45 min TTL),
  next candle evaluation, confirmation checklist, entry/stop/target, narratives
- **What Argus is doing** / **Why Argus decided** plain-language lines

EOC polls `/api/founder/cockpit` every 15s for live updates.

## Watching semantics

- `watching_since` persists across cycles for the same symbol while still Watching
- Opportunities **expire after 45 minutes** without confirmation (server-side)
- Countdowns on Home are derived from stored ISO timestamps, not invented timers

## Safety

- Paper / Live remain separated
- Coaching Take/Skip and idea marks (Good / Questionable / Bad) stay paper-only
- Stale prices are labeled; P&L is not shown as zero when marks are missing
- Reduced-motion preferences disable pulse animations
