# Argus Founder Quickstart

Operate Argus **without Cursor**. GitHub remains the source of truth for code; the Control Center and Founder Dashboard are how you run paper trading day to day.

**Milestone:** Founder RC1 — Daily Paper Operation (Sprint 5)  
**Provider:** `internal_paper`  
**Live trading:** Disabled (not certified)  
**Dashboard:** http://127.0.0.1:3000/overview  
**Foundation progress:** Phases 0–15 complete · Phase 16 planned (see `ROADMAP.md`)

## One-time setup

1. Ensure `.env` exists (copy from `.env.paper.example` or `.env.example`).
2. Bootstrap a Founder account if you do not already have one (see `docs/architecture/AUTHENTICATION.md`).
3. Optional — for the **Generate Daily Report** desktop shortcut, set in `.env` (never commit real values):

```
ARGUS_OPERATOR_USERNAME=founder
ARGUS_OPERATOR_PASSWORD=your-long-passphrase
```

4. Install Desktop shortcuts:

```powershell
.\scripts\control-center\install-desktop-shortcuts.ps1
```

Shortcuts created:

| Shortcut | Action |
| --- | --- |
| Start Argus | Infra + API + worker + EOC; opens dashboard |
| Stop Argus | Graceful stop; volumes preserved |
| Restart Argus | Stop then Start |
| Argus Status | Running/Stopped, provider, live disabled, backup |
| Backup Argus | Paper DB dump + integrity verify |
| Generate Argus Daily Report | Immutable paper daily report (CLI) |
| Open Argus Dashboard | http://127.0.0.1:3000/overview |

## Morning

1. Double-click **Start Argus**.
2. Sign in on the Founder Dashboard when prompted.
3. Confirm: Overall health, Provider `internal_paper`, Live trading **Disabled**, milestone strip shows Founder RC1.
4. Optional: double-click **Argus Status**.

## During the day

- Use **Open Argus Dashboard** for portfolio summary, open positions, paper P&L, and active alerts.
- Generate a daily paper report from the dashboard form (or the desktop shortcut).
- System Health holds runtime monitor, backup integrity, workers, and incident history.
- Cursor may be used for other projects — Argus does not require it to stay open.

## End of day

1. Optional: **Backup Argus**.
2. Optional: **Generate Argus Daily Report** (defaults to yesterday UTC).
3. Double-click **Stop Argus** if you want services off.
4. Postgres/Redis volumes are **preserved** (paper state is not wiped).

## Manual commands

```powershell
.\scripts\control-center\start-argus.ps1
.\scripts\control-center\stop-argus.ps1
.\scripts\control-center\restart-argus.ps1
.\scripts\control-center\status-argus.ps1
.\scripts\control-center\backup-argus.ps1
.\scripts\control-center\generate-daily-report.ps1
.\scripts\control-center\open-dashboard.ps1
```

## Notes

- First start may take a few minutes (Docker, migrate, Next.js compile).
- Logs: `runtime/control-center/*.log` (gitignored).
- Do not enable live trading from the Control Center — it remains deny-by-default.
- Daily reports are paper-only and immutable once generated for a calendar date.
