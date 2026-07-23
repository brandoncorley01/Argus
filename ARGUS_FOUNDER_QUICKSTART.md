# Argus Founder Quickstart

Operate Argus **without Cursor**. GitHub remains the source of truth for code; the Control Center and EOC are how you run paper trading day to day.

**Provider:** `internal_paper`  
**Live trading:** Disabled (not certified)  
**Dashboard:** http://127.0.0.1:3000/overview

## One-time setup

1. Ensure `.env` exists (copy from `.env.paper.example` or `.env.example`).
2. From the repo (PowerShell):

```powershell
.\scripts\control-center\install-desktop-shortcuts.ps1
```

This creates Desktop shortcuts: **Start Argus**, **Stop Argus**, **Argus Status**, **Open Argus Dashboard**.

## Morning

1. Double-click **Start Argus**.
2. Wait until the browser opens the Founder Dashboard (login if needed).
3. Confirm Status shows Running, Provider `internal_paper`, Live trading Disabled.

## During the day

- Use **Open Argus Dashboard** (or http://127.0.0.1:3000/overview).
- Cursor may be used for other projects — Argus does not require it to stay open.
- Paper trading, System Health, and incidents live in the EOC.

## End of day

- Double-click **Stop Argus** if you want services off.
- Postgres/Redis data volumes are **preserved** (paper state is not wiped).

## Manual commands (same launchers)

```powershell
.\scripts\control-center\start-argus.ps1
.\scripts\control-center\status-argus.ps1
.\scripts\control-center\open-dashboard.ps1
.\scripts\control-center\stop-argus.ps1
```

## Notes

- First start may take a few minutes (Docker, migrate, Next.js compile).
- Logs: `runtime/control-center/api.log` and `eoc.log` (gitignored).
- Do not enable live trading from the Control Center — it remains deny-by-default.
