# Trading Intelligence (Observational)

Paper only. Never unlocks live trading. Never auto-tunes strategy rules.

## Purpose

Increase Founder confidence that Argus makes good paper decisions before any
real capital is considered.

## Systems

- **Trade Confidence** — numeric 0–100 + High/Medium/Low label
- **Trade Explanation** — plain-language reason stored on entry
- **Market Regime** — trend_up / trend_down / volatile / quiet / insufficient_data
- **Strategy Performance** — observational aggregates by strategy key
- **Missed Opportunity Tracking** — expired bullish watches evaluated later
- **Post Trade Review** — outcome, drawdown, holding time, exit reason, regime

## Founder surface

Home shows one **Trading Intelligence** section with at most five bullets.
Detailed intelligence is in Daily Reports and API routes under
`/api/v1/operations/trading-intelligence/*`.

## Certification gate

Informational only. Criteria are tracked in `founder_certification_state` and
`GET .../trading-intelligence/certification`. Meeting criteria never enables live.
