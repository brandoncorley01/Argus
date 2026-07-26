# Trading Intelligence (Observational) — PROVE mode

Paper only. Never unlocks live trading. Never auto-tunes strategy rules.

## Purpose

Increase Founder confidence that Argus makes good paper decisions before any
real capital is considered. Argus is in **PROVE** mode after institutional readiness.

## Systems

- **Trade Confidence** — numeric 0–100 + High/Medium/Low + contributing factors (`confidence@2`)
- **Trade Explanation** — plain-language reason stored on entry
- **Watchlist Intelligence** — Scanning → Watching → Building Confidence → Ready → Executed
- **Case Files** — permanent decision timeline per candidate
- **Thinking Engine** — concise observations on meaningful state only
- **Morning Mission / EOD Debrief** — Founder mission control
- **Market Regime** — trend_up / trend_down / volatile / quiet / insufficient_data
- **Strategy Performance** — observational aggregates by strategy key
- **Missed Opportunity Tracking** — expired bullish watches evaluated later
- **Post Trade Review** — outcome, drawdown, MFE, holding time, exit reason, would-take-again

## Founder surface

Home shows an **Executive Briefing**:

- Institution status, Today's P&L, open positions
- Trading mission
- Intelligence summary (≤5 bullets)
- Highest priority opportunity
- Certification progress
- Founder action required
- Expandable Live Market Intelligence (top 5 watchlist only)

Desk/cockpit tools remain available but collapsed.

## API

- `GET /api/v1/operations/trading-intelligence/briefing`
- `GET /api/v1/operations/trading-intelligence/certification`
- `GET /api/v1/operations/trading-intelligence/learning`
- `GET /api/v1/operations/trading-intelligence/watchlist`
- `GET /api/v1/operations/trading-intelligence/mission`
- `GET /api/v1/operations/trading-intelligence/debrief`
- `GET /api/v1/operations/trading-intelligence/case-files/{candidate_id}`

## Certification gate

Informational only. Criteria are tracked in `founder_certification_state` and
`GET .../trading-intelligence/certification`. Meeting criteria never enables live.
