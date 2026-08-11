# Argus

## Daily use (browser)

1. Open http://127.0.0.1:3000
2. Sign in
3. On **Home**:
   - **Start Argus** (when Stopped) or **Update from GitHub** (when Running) — both hard-sync `main`
   - **Pause New Trades** to block new paper entries while open positions can still be managed
   - **Refresh recent prices**, then **Scan markets now**
4. Confirm Build shows **live-monitor-v2.48** (or newer). Also check Desktop `Argus-last-start.txt` says `GitHub sync: MATCH`.
5. Watch the **Live Trading Cockpit** and market wall (real scan progress + countdowns)
6. Use **Paper Training** for Automatic Practice or Coaching Mode (Take / Skip / feedback / scorecard)

Primary nav: Home · Paper Training · Trades · Reports · Settings.

Paper funds are never real money. Live unlock is not available from Home or from Live Readiness.

## If Build stays stuck on an old stamp (e.g. still v2.40)

Cloud agent saves only to GitHub — not to a folder on this PC.
**Do this first** (PowerShell, GitHub API — not CDN):

```powershell
iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/diagnose-argus-folder.ps1?ref=main')
iex (irm -Headers @{Accept='application/vnd.github.raw'} 'https://api.github.com/repos/brandoncorley01/Argus/contents/scripts/control-center/update-argus-now.ps1?ref=main')
```

Or double-click Desktop **`FIX PC Argus`** / **`GET-LATEST.cmd`** / **`FIX-PC.cmd`**.

Then:
1. Desktop **`Argus-folder-report.txt`** — ACTIVE folder vs GitHub TARGET
2. Desktop **`Argus-update-report.txt`** — TARGET/LOCAL/HTTP must match
3. Open http://127.0.0.1:3000/argus-build.txt — must say **live-monitor-v2.48**
4. Hard-refresh Home (**Ctrl+F5**) — Build chip must match

If ACTIVE folder ≠ the folder you thought you were updating, that is why Home stayed on v2.40.

## If the browser says “refused to connect”

The dashboard is not running. Do **not** keep refreshing `127.0.0.1` alone.

1. In your Argus folder, double-click **`Start-Argus.cmd`**
2. Wait until the black window finishes (can take a few minutes; Docker must be running)
3. Open exactly: **http://127.0.0.1:3000/today** (the `:3000` matters)
4. Sign in and confirm Build **live-monitor-v2.48** (or newer)

Faster option if Start already failed once: double-click **`Recover-Dashboard.cmd`**.

## If Start is stuck on “Starting…” / “Working…”

1. Press **F5** (or close the tab and reopen http://127.0.0.1:3000/today)
2. Click **Start Argus** / **Update from GitHub** once more and wait (can take a few minutes)
3. If the page is blank/dead or refused to connect, use **`Start-Argus.cmd`** as above

Browser Start must not kill the dashboard mid-request. Fixed Start scripts leave the page up and soft-refresh.

See `docs/operations/PAPER_TRAINING_LAB.md` and `docs/operations/FOUNDER_COMMAND_CENTER.md`.
