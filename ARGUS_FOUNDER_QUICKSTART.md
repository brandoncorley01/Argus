# Argus Founder Quickstart

Operate Argus **without Cursor**.

**Home:** http://127.0.0.1:3000/today  
**Paper trading:** Active path  
**Live trading:** Locked

## One-time setup

1. Ensure `.env` exists.
2. Bootstrap a Founder account if needed (`docs/architecture/AUTHENTICATION.md`).
3. Install shortcuts:

```powershell
.\scripts\control-center\install-desktop-shortcuts.ps1
```

### ARGUS — DAILY (use these)

| Shortcut | What it does |
| --- | --- |
| **Start Argus** | Starts everything and opens Home |
| **Open Argus** | Opens Home (status + Start/Stop) |
| **End Trading Day** | Report + backup (does not stop Argus) |
| **Stop Argus** | Stops services; keeps your paper data |

### ARGUS — TOOLS (optional)

Status · Restart · Backup · Generate Daily Report

## Morning

1. Double-click **Start Argus**
2. Sign in
3. On **Home**, confirm status is **Running**
4. That’s it

## During the day

- Stay on **Home** for Start / Stop / status
- Use **Trading** / **Portfolio** / **Reports** only when you want detail
- Ignore **Advanced…** unless something is wrong

## End of day

1. **End Trading Day** (or the button on Home)
2. **Stop Argus**

## Manual commands

```powershell
.\scripts\control-center\start-argus.ps1
.\scripts\control-center\status-argus.ps1
.\scripts\control-center\end-trading-day.ps1
.\scripts\control-center\stop-argus.ps1
```

## Notes

- First start can take a few minutes
- Logs: `runtime/control-center/*.log`
- Live trading remains locked
