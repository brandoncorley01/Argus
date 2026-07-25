# Argus

## Daily use (browser)

1. Open http://127.0.0.1:3000
2. Sign in
3. On **Home** (Command Center):
   - **Start Argus** / **Stop Argus** for the system
   - **Pause New Trades** to block new paper entries while open positions can still be managed
4. Confirm build shows **command-center-v2** (or newer)
5. Use the account summary, active trades, and activity feed to confirm Argus is working

Paper funds are never real money. Live unlock is not available from Home.

## If Start is stuck on “Starting…” / “Working…”

1. Press **F5** (or close the tab and reopen http://127.0.0.1:3000/today)
2. Click **Start Argus** once more and wait (can take a few minutes)
3. If the page is blank/dead, double-click `Start-Argus.cmd` on the PC, wait, then sign in again

Browser Start must not kill the dashboard mid-request. Fixed Start scripts leave the page up and soft-refresh.

See `docs/operations/FOUNDER_COMMAND_CENTER.md` for data sources and unavailable metrics.
