# Argus

## Daily use (browser)

1. Open http://127.0.0.1:3000
2. Sign in
3. On **Home**:
   - **Start Argus** / **Stop Argus** for the system
   - **Pause New Trades** to block new paper entries while open positions can still be managed
   - **Refresh recent prices**, then **Scan markets now**
4. Confirm build shows **paper-training-lab-v1** (or newer)
5. Use **Paper Training** for Automatic Practice or Coaching Mode (Take / Skip / feedback / scorecard)

Primary nav: Home · Paper Training · Trades · Reports · Settings.

Paper funds are never real money. Live unlock is not available from Home or from Live Readiness.

## If the browser says “refused to connect”

The dashboard is not running. Do **not** keep refreshing `127.0.0.1` alone.

1. In your Argus folder, double-click **`Start-Argus.cmd`**
2. Wait until the black window finishes (can take a few minutes; Docker must be running)
3. Open exactly: **http://127.0.0.1:3000/today** (the `:3000` matters)
4. Sign in and confirm build **paper-training-lab-v1**

Faster option if Start already failed once: double-click **`Recover-Dashboard.cmd`**.

## If Start is stuck on “Starting…” / “Working…”

1. Press **F5** (or close the tab and reopen http://127.0.0.1:3000/today)
2. Click **Start Argus** once more and wait (can take a few minutes)
3. If the page is blank/dead or refused to connect, use **`Start-Argus.cmd`** as above

Browser Start must not kill the dashboard mid-request. Fixed Start scripts leave the page up and soft-refresh.

See `docs/operations/PAPER_TRAINING_LAB.md` and `docs/operations/FOUNDER_COMMAND_CENTER.md`.
