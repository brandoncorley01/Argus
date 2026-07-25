# Live Trading Cockpit

Build id: `trading-cockpit-v1.5`.

Home is a live **Trading Cockpit** with heartbeat dials driven by verified scan,
price, and paper-account updates. Motion reflects real poll ages and mark
changes — Argus does not invent heartbeats, prices, or P&L.

## Eastern time

Founder-facing timestamps use **US Eastern** (`America/New_York`, EST/EDT) with
a fixed zone so server HTML matches the browser.

## Short-timeframe scanning (v1.5)

Argus evaluates opportunities on **1m and 5m** charts (not 15m-first):

- Worker **auto-scans every minute** when Start Argus has the health-supervisor
  worker running
- Price refresh pulls Coinbase **1m/5m** candles (about every 2 minutes, and
  again immediately before a scan if bars are older than ~90 seconds)
- Next-evaluation countdown uses the active short candle length (1 or 5 minutes)
- Watch window is **20 minutes** so ideas do not sit through long unused intervals

If scans look idle, check that the worker is up (`status-argus` / worker.log) and
press **Refresh recent prices**, then wait for the next one-minute cycle.

## Heartbeat dials

Polled every **5 seconds**:

- Argus pulse (cockpit fetch age)
- Price feed age
- Scan cycle countdown (1-minute scans)
- Watching count
- Open paper trades
- Open unrealized P&L (verified marks only)
- Closed realized P&L

## Paper money path (honest)

1. **Coaching (default):** Argus watches ideas; you press **Take** to open a
   simulated trade.
2. **Automatic Practice:** after each scan, Argus may enter Watching + risk-clear
   candidates (paper only, risk checks still apply).
3. **Exits:** when an entry opens, planned stop/target are stored on the order.
   On later scans / price refresh, Argus sells the paper position if the verified
   mark hits stop or take-profit. Realized P&L then appears on the Closed dial.

Live trading remains locked. No fabricated activity.

## Crash recovery

- Cockpit returns degraded empty snapshots instead of blanking Home
- `migrate-up.ps1` verifies/repairs `paper_training_settings` via API venv Python
