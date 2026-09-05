# Changelog

All notable changes to Argus are recorded here.
Format follows a simple keep-a-changelog style adapted for institutional releases.

## [Unreleased]

### Added

- Regime-aware crypto bot strategy families in Strategy Lab + paper Alpha Radar: `grid_trading` (sideways), `dca` (dip averaging), `trend_momentum` (RSI+MACD), `cross_venue_arb` (verified secondary prices only); confidence scoring prefers strategy×regime fit; `GET /api/v1/strategies/registry` catalog (`live-monitor-v2.57`)

### Changed

- **Cloud-agent accountability:** every product-behavior job must bump Build live monitor (`apps/eoc/public/argus-build.txt` + `ARGUS_UI_BUILD`) or the job is incomplete (`live-monitor-v2.60`)
- **Paper bots actually trade:** Founder Learning Desk auto-forced to Automatic on each scan worker cycle; `dca` / `trend_momentum` / `grid_trading` skip memory WAIT/AVOID burial; Bitsgap-style interval DCA buys majors every 4h; softer DCA/trend detectors (`live-monitor-v2.59`)
- Paper P&L path: Learning Desk auto-forces Automatic Practice; ticket $100→$150; stop 2% / 1.5R reachable targets; remove 120s take-profit hold handicap; easier EXECUTE memory gate; less chase/regime haircut so Argus actually enters and can bank dollars in paper (`live-monitor-v2.58`)
- **Join-Path ChildPath hang:** updater had `Join-Path "C:\Argus"` (one arg) which prompted Founder for ChildPath; fixed in v15 (`live-monitor-v2.56`)
- **Git stderr Start crash:** WinPS treated `git fetch` progress (`From https://...`) as fatal under `$ErrorActionPreference=Stop`; `Invoke-ArgusGit` + updater v14 (`live-monitor-v2.55`)
- **Desktop only (no OneDrive):** canonical PC folder is `%USERPROFILE%\Desktop\Argus`; updater v13 / bring-up v2 never Start from OneDrive; shortcuts install to real Desktop (`live-monitor-v2.54`)
- **PSObject op_Addition crash:** updater v12 reorders ACTIVE folder with List (WinPS crashed when OneDrive + Desktop both found); sync OneDrive\Desktop\Argus first (`live-monitor-v2.53`)
- **Bring Argus up:** `bring-argus-up.ps1` / `Bring-Argus-Up.cmd` finds or clones folder and Start (`live-monitor-v2.52`)
- **No folder / cannot find file:** updater v11 clones `Desktop\Argus` from GitHub when no git checkout exists; reports written to Desktop + OneDrive Desktop + profile (`live-monitor-v2.51`)
- **WinPS GitHub parse:** updater v10 decodes `[byte[]]` / JSON+base64 Contents API bodies and prefers plain `public/argus-build.txt` for TARGET (`live-monitor-v2.50`)
- **404 stamp proof:** `/argus-build.txt` App Router route + `/api/argus-build` so a missing `public/` file cannot 404 forever; 404 = stale PC tree still not on main (`live-monitor-v2.49`)
- **Deep PC sync fix:** Start refuses Fast Start when HTTP `/argus-build.txt` ≠ this folder’s build (kills foreign `:3000`); Home Update runs nuclear `update-argus-now`; Desktop Update shortcut uses GitHub API (not local stale .ps1); `FIX-PC.cmd`; no raw CDN fallback (`live-monitor-v2.48`)
- **PC folder proof:** `diagnose-argus-folder.ps1` reports Start shortcut WorkDir, which folder serves `:3000`, and GitHub TARGET; updater v7 prefers the live dashboard folder (`live-monitor-v2.47`)
- **CDN lag root cause:** Start/updater now pull scripts + TARGET build via GitHub Contents API (raw.githubusercontent.com was still serving v2.44 after main was v2.45); `update-argus-now-v6` + `GET-LATEST.cmd` (`live-monitor-v2.46`)
- **Stuck-on-v2.40 escape:** `update-argus-now-v5` syncs every Argus checkout to GitHub TARGET build, verifies HTTP `/argus-build.txt`, refuses Start when script self-update fails; add `GET-LATEST.cmd` (`live-monitor-v2.45`)
- **Cloud-agent sync hard fix:** every Start hard-resets to GitHub main before Fast Start; fetch failures no longer pretend “up to date”; Desktop `Argus-last-start.txt` proves MATCH/MISMATCH; Home **Update from GitHub** works while Running; add `Update-Argus.cmd` (`live-monitor-v2.44`)
- CI mypy green: harden discovery state load and discovery sample join types (`live-monitor-v2.43`)
- Widen Alpha Radar for Coinbase strong-day runners: discovery every 5m; probe 140 / promote 35; refresh 72 symbols; stop hard-rejecting late-stage near-highs (only extreme peak tip blocked); longer Watching TTL; slightly easier memory EXECUTE — so Argus stops missing runs while still refusing tip-chase (`live-monitor-v2.42`)
- Meaningful paper P&L sizing: Founder Learning Desk default practice size $30→$100 (~33% of $300 book); enforce 1.5% minimum stop distance and $3 minimum planned reward so winning days are dollars, not pennies; auto-upgrade legacy $30 desks when cash allows (`live-monitor-v2.41`)

### Added

- Dynamic Coinbase USD market discovery: periodically lists active USD products, ranks sudden interest, filters liquidity/spread/volatility/chase risk, promotes a capped set into Alpha Radar; compact Market Discovery card on Live Desk; Academy tracks discovery outcomes (`live-monitor-v2.36`)
- Argus Academy learning loop: institutional memory consults before automatic paper entries (EXECUTE/WAIT/AVOID); decision quality independent of P&L; PAPER detectors (momentum, breakout, dip/pullback, range, peak protection); readiness uses % drawdown + memory reuse (`live-monitor-v2.33`)
- Argus Academy surface restored on nav + `/paper-training` (learning desk, capital recovery, Advanced Learning) (`live-monitor-v2.34`)
- Live Desk clarity: discovery tiles pop in and log when new coins hit Radar; stronger real-time scan spotlight; denser panels collapsed into Watching / Scan log / Filtered (`live-monitor-v2.37`)

### Fixed

- Executive Briefing on Home was hardcoded empty (`briefing={null}`); it now loads/polls live briefing with watchlist + discovery context (`live-monitor-v2.40`)
- Market discovery actually runs on Start Argus: register discovery cron on the health-supervisor worker (the process Start launches) and persist discovery state under repo `runtime/` (`live-monitor-v2.39`)
- Fix paper portfolio list 500: use SQLAlchemy `case(...)` (not `func.case`) so Home/Academy can load desks (`live-monitor-v2.38`)
- Cockpit load + capital story: OHLCV bar queries use LIMIT (fixes 15s cockpit 502); Home explains $300→remaining cash via paper fills; auto-enter pauses when cash below notional (`live-monitor-v2.24`)
- Unattended hard fix: keep-awake stays up while desired=Running (no longer exits on brief API blips); keepalive requires API+worker; scan automation uses isolated DB sessions; catch-up cooldown stops scan storms (`live-monitor-v2.23`)
- Paper capital accuracy: hydrate in-memory book from DB before every order (stops position wipe / cash desync after API restart); Home/Portfolio show cash_balance + mark equity; learning-desk endpoint restored (`live-monitor-v2.22`)
- Home Start always force-syncs GitHub main, rewrites `/argus-build.txt` on every Start path, and recycles the dashboard when the Build chip was stale (`live-monitor-v2.21`)
- PowerShell no longer flashes at random: ArgusKeepAlive / keep-awake / Home Start-Stop / login recovery / backup launch via `run-hidden.vbs` (wscript window style 0); Start self-updates and re-registers the hidden task (`live-monitor-v2.20`)
- API failure recovery: recreate missing/broken API venv, migrate during repair, dump api.err.log, add `repair-argus-api.ps1` (`live-monitor-v2.19`)
- Home Build chip reads live `/argus-build.txt`; `update-argus-now.ps1` writes Desktop report + verifies HTTP stamp (`live-monitor-v2.18`)
- Start always overwrites control-center scripts from GitHub (dirty local Start scripts no longer block refresh); add `update-argus-now.ps1` one-command hard reset (`live-monitor-v2.17`)
- Start no longer skips GitHub sync on Fast Start when this PC is behind `main`; self-updates `_common.ps1` + schedules dashboard recycle so Home leaves stale build stamps (`live-monitor-v2.16`)
- PowerShell console popups: ArgusKeepAlive scheduled task is Hidden, keep-awake uses CreateNoWindow, and background Start/EOC/login recovery shells pass `-WindowStyle Hidden` (`live-monitor-v2.14`)

### Added

- Advanced Paper Learning Engine: 20-day PAPER cycle with milestones, strategy leaderboard, high-volume Opportunity Radar inputs, bounded adaptive confidence, Day-20 readiness report (never enables live), Advanced Learning pane on Paper Training (`live-monitor-v2.13`)

### Fixed (earlier)

- Unattended runtime: Start Argus launches a Windows keep-awake helper so automatic sleep/hibernate does not silently stop paper scans; Stop releases it
- Worker wake catch-up: health supervisor detects ≥90s wall-clock gaps (and startup) and forces price refresh + scan so automation resumes without Founder clicks
- Live desk feel: Eastern live clock, Decided pane ages ticking every second, faster Home polls, and visibility/wake refresh so Argus feels alive without constant attention

### Added (foundation)

- Phase 5 authentication: Argon2id passwords, PostgreSQL server-side sessions, CSRF, login lockout, Founder bootstrap CLI
- RBAC enforcement for Founder-only user/role management; audit reads require authentication
- Phase 6 configuration/policy versioning: lifecycle statuses, canonical payload hashing, secret detection, atomic activation with Institutional Identity updates, HTTP APIs under `/api/v1/configurations` and `/api/v1/policies`
- Phase 7 operating-mode state machine: singleton authoritative state, transition matrix, durable idempotency, emergency fail-closed doctrine, APIs under `/api/v1/operating-mode`
- Phase 8 institutional health supervisor and worker foundation: governed service registry, append-only heartbeats, projections, durable supervisor lease, incidents/lifecycle, protective actions, ARQ worker, SYSTEM `SAFE_MODE` integration
- Phase 9 Executive Operations Center (`apps/eoc`): Next.js App Router BFF session bridge, role-aware dashboards, operations/services/workers/incidents/audit/configurations/policies/administration — real API state only
- Phase 10 Market Intelligence Platform: multi-provider registry, historical OHLCV/news/calendar/research storage, replay-safe ingest, quality monitoring, `/api/v1/market` APIs, EOC `/market` — observation only
- Phase 11 Strategy Laboratory: governed strategy versions, deterministic backtest/walk-forward/optimization/Monte Carlo, validation reports, `/api/v1/strategies`, EOC `/strategies` — research only
- Phase 12 Paper Trading Institution: Execution Gateway, Internal Paper Provider (default), portfolios/orders/fills/P&L/risk/replay, `/api/v1/paper`, EOC `/paper` — no brokerage account required
- Phase 13 Micro-Live Institution: deny-by-default live-execution architecture — `live_activation_state` machine (default `PAPER_ONLY`, no reachable path to `MICRO_LIVE_ACTIVE`), credential referencing (env var names only, never values), kill switches, versioned micro-capital policy, fixture-based reconciliation, `ExecutionGateway.assert_live_allowed`, optional disabled adapter scaffolds (Coinbase/Kraken/IBKR), `/api/v1/micro-live`, EOC `/micro-live` — live trading remains disabled; no credentials required
- Phase 14 Treasury and Executive Analytics: simulated-ledger treasury accounts/pools/allocations/reservations, append-only internal ledger, external transfer *instructions* with execution structurally forbidden (`external_transfer_execution_forbidden`, no `executed` status exists), performance attribution and executive KPIs built from real paper/health/incident/strategy data (never invented), deterministic forecast scenarios, immutable content-hashed institutional reports with paper/live disclaimers, `/api/v1/treasury`, EOC `/treasury` — no real money movement possible
- Phase 15 Operational Validation: System Health dashboard API + EOC, host CPU/memory/disk snapshots, operational event log with severities and correlation IDs, immutable daily paper trading reports, health-supervisor crons — `internal_paper` only
- Governance frameworks: Engineering Constitution, Phase Execution, Independent Review, Release Certification
- RC1 finalization: minimal CI, backup/restore scripts, durable RC evidence

### Planned

- Phase 16 Hardening & CI follow-ups (remote CI soak, optional multi-week paper tooling)

## [0.1.0-foundation] — 2026-07-16

### Added

- Project governance baseline (`AGENTS.md`, ADRs 001–007, institutional identity/maturity/feature docs)
- Docker Compose foundation for PostgreSQL 16 and Redis 7 with operator scripts
- FastAPI control-plane skeleton with fail-closed settings and `/health` / `/ready`
- Alembic-managed institutional domain schema (identity, users/roles, audit, config/policy versions, feature registry, maturity, system state, incidents, health events)
- Fail-closed audit service and read API (`GET /api/v1/audit/events`)

### Security

- Live trading modes (`MICRO_LIVE`, `NORMAL_LIVE`) remain permanently locked in v0.1
- Secrets excluded via `.gitignore`; `.env.example` documents required variables only
- Audit payloads redact sensitive keys before persistence

### Notes

- No exchange integrations, market data, strategies, execution, leverage, margin, futures, options, short selling, or withdrawals
- No public remote configured in early local development; commits remain local unless explicitly pushed
