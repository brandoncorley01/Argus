# Argus keepalive after reboot

Argus keeps the **dashboard (EOC)** up independently of the **API**. After Stop,
or after a reboot, login fails until Postgres/Redis + the local API are up again.

For **automatic sleep/hibernate prevention** while Running and wake catch-up,
see [`UNATTENDED_RUNTIME.md`](UNATTENDED_RUNTIME.md).

## What is automatic

1. **Start Argus** writes `runtime/control-center/desired-state.json` with
   `running: true` and registers the Windows scheduled task `ArgusKeepAlive`
   (then starts that task once immediately).
2. **ArgusKeepAlive** runs at user logon and every 2 minutes via
   `wscript.exe` + `run-hidden.vbs` (window style 0 — no PowerShell console
   popups; `-WindowStyle Hidden` alone still flashes on many PCs). While desired
   state is Running it:
   - launches Docker Desktop if the engine is down
   - starts `postgres` / `redis` and waits until healthy
   - starts local uvicorn (API) and the health-supervisor worker if missing
   - appends to `runtime/control-center/keepalive-task.log`
3. **Stop Argus** sets `running: false` first so keepalive does not fight Stop.
4. The **login page** probes Docker / Postgres / Redis / API and triggers the
   same recovery when the API is unreachable (never invents a healthy response).
5. **Start / infra-up** never silently `git reset --hard`. Dirty trees skip sync
   unless `ARGUS_FORCE_SYNC=1`. Start script self-update also skips dirty local
   `start-argus.ps1` unless that flag is set.

Compose already uses `restart: unless-stopped` for postgres and redis so they
return after Docker Desktop itself restarts (unless you intentionally Stopped).

## What you may still need once after reboot

1. **Sign in to Docker Desktop** if it prompts (first boot / update) — Argus
   cannot complete that for you.
2. If you Left Argus **Stopped** before reboot, press **Start Argus** once
   (desktop shortcut or Home). Desired state stays Stopped until you do.
3. If you Left Argus **Running**, wait ~1–2 minutes after Windows logon (or open
   the login page) — keepalive should restore API without another click.

## Manual checks

```powershell
.\scripts\control-center\status-argus.ps1
.\scripts\control-center\keep-argus-alive.ps1
```

Paper trading only. Live trading remains disabled.
