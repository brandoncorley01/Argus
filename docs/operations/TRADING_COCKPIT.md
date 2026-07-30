# Live Trading Cockpit

Build id: `alive-unattended-v3.1`.

Home is a live **Trading Cockpit** with heartbeat dials driven by verified scan,
price, and paper-account updates. Motion reflects real poll ages and mark
changes — Argus does not invent heartbeats, prices, or P&L.

See also [`UNATTENDED_RUNTIME.md`](UNATTENDED_RUNTIME.md) for keep-awake and
wake catch-up (Argus stays Running until Stop; automatic sleep is blocked).

## Eastern time

Founder-facing timestamps use **US Eastern** (`America/New_York`, EST/EDT) with
a fixed zone so server HTML matches the browser.

## Desk layout (v1.7)

- **Live desk** — status chips + dials (pulse, prices, next scan, watching, open, P&L)
- **Live monitor** — per-market board with ticking feed age / last-seen (replaces the
  frozen “Now” essay that stuck on “monitoring N”)
- **Update prices** (feed) vs **Re-score now** (brain) are separate action cards
- Practice mode toggle: **You approve** / **Auto enter**
- Market wall tiles show a freshness dot; focus panel uses check glyphs and plan meters
- Home keepalive every ~30s: if the 1m/5m feed is ≥90s old, Home pulls prices
  (worker still owns the primary cadence); wake/visibility also triggers catch-up
- Live Eastern clock + Decided ages tick every second
- Cockpit / paper pulse poll about every **4s**
- Watch window is **8 minutes** on short-TF setups so watches do not pile up

## Short-timeframe scanning

Argus evaluates opportunities on **1m and 5m** charts (not 15m-first):

- Worker **auto-scans every minute** when Start Argus has the health-supervisor
  worker running
- Price refresh pulls Coinbase **1m/5m** candles (about every 2 minutes, and
  again immediately before a scan if short-TF bars are older than ~90 seconds)
- Feed age uses **1m/5m closes only** (a fresh 15m bar cannot hide a stale short book)
- Bars older than **5 minutes** are stale for short-TF practice
- Watch window is **8 minutes**

If the feed looks old, wait briefly for automatic catch-up, or press
**Update prices**. Confirm the worker and keep-awake are up (`status-argus` /
worker.log / keep-awake.log).

## Heartbeat dials

Polled every **4 seconds**:

- Argus pulse (cockpit fetch age)
- Price feed age
- Scan cycle countdown (1-minute scans)
- Watching count
- Open paper trades
- Open unrealized P&L (verified marks only)
- Closed realized P&L

## Paper money path (honest)

1. **Coaching (default):** Argus watches ideas; you press **Take (paper)** to open a
   simulated trade.
2. **Automatic Practice:** after each scan, Argus may enter Watching + risk-clear
   candidates (paper only, risk checks still apply).
3. **Exits:** when an entry opens, planned stop/target are stored on the order.
   On later scans / price refresh, Argus sells the paper position if the verified
   mark hits stop or take-profit. Realized P&L then appears on the Closed dial.

Live trading remains locked. No fabricated activity.

## Crash recovery

- Cockpit returns degraded empty snapshots instead of blanking Home
- `migrate-up.ps1` waits for PostgreSQL, retries alembic, then verifies/repairs
  `paper_training_settings` via API venv Python
- If Start fails on a SQLAlchemy connection traceback: open **Docker Desktop**,
  confirm `docker compose ps` shows postgres healthy, check `.env` passwords,
  then Start Argus again
