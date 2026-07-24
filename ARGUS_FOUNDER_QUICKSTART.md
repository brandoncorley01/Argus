# Argus

## Daily use

1. Open http://127.0.0.1:3000
2. Sign in
3. On **Home**, press **Start Argus** or **Stop Argus**

You should see **UI build: home-start-stop-v1** at the bottom of Home.

## If Home still looks old (no Start / Stop)

Paste this in PowerShell:

```powershell
irm https://raw.githubusercontent.com/brandoncorley01/Argus/main/scripts/control-center/force-home-update.ps1 | iex
```

That pulls GitHub `main`, restarts Argus, and opens the new Home.

Live trading stays locked. Paper data is kept when you stop.
