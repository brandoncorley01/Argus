# Unattended runtime (keep-awake + catch-up)

Build id: `live-monitor-v2.23`.

Argus is local-first on the Founder PC. While **Start Argus** has left the
system Running, Argus should keep working without babysitting until **Stop
Argus** or a real loss of connection (Docker/API/worker down).

Companion: [`ARGUS_KEEPALIVE.md`](ARGUS_KEEPALIVE.md) covers reboot recovery
(Docker/API/worker restart via scheduled task). This doc covers **host sleep
prevention** and **wake catch-up**.

## Keep-awake (blocks automatic sleep)

On every successful Start path, Control Center launches
`scripts/control-center/keep-awake-argus.ps1`. That helper pulses Windows
`SetThreadExecutionState` (`ES_SYSTEM_REQUIRED` + `ES_AWAYMODE_REQUIRED` when
supported) about every 30 seconds **while desired state is Running**.

- Automatic sleep / hibernate timeouts are blocked while Running.
- The helper does **not** exit when API/worker are briefly down (that used to
  release sleep protection and leave Argus dark for days).
- The display may still dim (by design — saves power).
- **Stop Argus** sets desired=Stopped; the helper then releases and exits.
- Status: `status-argus.ps1` shows `Keep-awake: up (blocks automatic sleep)`.
- Log: `runtime/control-center/keep-awake.log`.
- Keep-awake and keepalive helpers launch through **`run-hidden.vbs`**
  (`wscript` window style 0) so PowerShell does not flash on the desktop.

Forced hibernate (user choosing Hibernate, lid policies that ignore away
mode, or critical battery) can still suspend the machine. On resume, catch-up
below recovers without requiring a Founder click.

## Keepalive health bar

`ArgusKeepAlive` only reports healthy when **API /ready and the ARQ worker
are both up**. API-only was previously treated as success, which left Home
looking Running with no scans and no fresh data.

## Wake / downtime catch-up

The health-supervisor worker tracks wall-clock time between 30s health cycles.

- Gap ≥ **90 seconds** ⇒ treat as host sleep/suspend (or long pause).
- Worker **startup** always schedules one catch-up.
- Catch-up = verified **price refresh** + **forced market scan** (exits/entries
  still go through existing paper risk rules).

Home also recovers without attention:

- Cockpit / paper pulse poll every **4s**.
- Tab `visibilitychange` and late interval fires trigger an immediate refresh.
- Keepalive price refresh runs about every **30s** when the feed is stale, and
  on wake when the feed is older than ~45s.

## Live desk feel

- Eastern **live clock** ticks every second on the command bar and Live desk.
- **Decided** pane shows relative ages (`12s ago`) that update every second,
  backed by real decision timestamps (never fabricated).
- Status copy: Running means Argus works until Stop; sleep is blocked while up.

## Honesty bounds

- Keep-awake cannot override a manual Hibernate or a dead Docker/API.
- Catch-up never invents prices, fills, or P&L.
- Live trading remains disabled.
