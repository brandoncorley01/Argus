# Changelog

All notable changes to Argus are recorded here.
Format follows a simple keep-a-changelog style adapted for institutional releases.

## [Unreleased]

### Added

- Live Desk clarity: discovery tiles pop in and log when new coins hit Radar; stronger real-time scan spotlight; denser panels collapsed into Watching / Scan log / Filtered (`live-monitor-v2.37`)
- Dynamic Coinbase USD market discovery: periodically lists active USD products, ranks sudden interest, filters liquidity/spread/volatility/chase risk, promotes a capped set into Alpha Radar; compact Market Discovery card on Live Desk; Academy tracks discovery outcomes (`live-monitor-v2.36`)
- Argus Academy learning loop: institutional memory consults before automatic paper entries (EXECUTE/WAIT/AVOID); decision quality independent of P&L; PAPER detectors (momentum, breakout, dip/pullback, range, peak protection); readiness uses % drawdown + memory reuse (`live-monitor-v2.33`)
- Argus Academy surface restored on nav + `/paper-training` (learning desk, capital recovery, Advanced Learning) (`live-monitor-v2.34`)

### Fixed

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
