# Argus

## Daily use (browser)

1. Open http://127.0.0.1:3000
2. Sign in
3. On **Home**:
   - **Start Argus** (when Stopped) or **Update from GitHub** (when Running) — both hard-sync `main`
   - **Pause New Trades** to block new paper entries while open positions can still be managed
   - **Refresh recent prices**, then **Scan markets now**
4. Confirm Build shows **live-monitor-v2.44** (or newer). Also check Desktop `Argus-last-start.txt` says `GitHub sync: MATCH`.
5. Watch the **Live Trading Cockpit** and market wall (real scan progress + countdowns)
6. Use **Paper Training** for Automatic Practice or Coaching Mode (Take / Skip / feedback / scorecard)

Primary nav: Home · Paper Training · Trades · Reports · Settings.

Paper funds are never real money. Live unlock is not available from Home or from Live Readiness.

## If Build stays stuck on an old stamp (cloud-agent merges not landing)

1. Double-click **`Update-Argus.cmd`** in the Argus folder (or Desktop **Update Argus Now**)
2. Wait for the report — Desktop `Argus-update-report.txt` / `Argus-last-start.txt`
3. Hard-refresh Home (**Ctrl+F5**)
4. Build must show the new `live-monitor-v2.xx`

## If the browser says “refused to connect”

The dashboard is not running. Do **not** keep refreshing `127.0.0.1` alone.

1. In your Argus folder, double-click **`Start-Argus.cmd`**
2. Wait until the black window finishes (can take a few minutes; Docker must be running)
3. Open exactly: **http://127.0.0.1:3000/today** (the `:3000` matters)
4. Sign in and confirm Build **live-monitor-v2.44** (or newer)

Faster option if Start already failed once: double-click **`Recover-Dashboard.cmd`**.

## If Start is stuck on “Starting…” / “Working…”

1. Press **F5** (or close the tab and reopen http://127.0.0.1:3000/today)
2. Click **Start Argus** / **Update from GitHub** once more and wait (can take a few minutes)
3. If the page is blank/dead or refused to connect, use **`Start-Argus.cmd`** as above

Browser Start must not kill the dashboard mid-request. Fixed Start scripts leave the page up and soft-refresh.

See `docs/operations/PAPER_TRAINING_LAB.md` and `docs/operations/FOUNDER_COMMAND_CENTER.md`.
