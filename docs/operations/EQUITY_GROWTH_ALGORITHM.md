# Equity Growth Algorithm (EGA)

Build id: `live-monitor-v2.96`. Module: `apps/api/app/services/equity_growth_algorithm.py`.

## Ownership

**Cursor owns success of this algorithm** inside Argus paper trading:

- design and implement deploy rules that target equity growth after costs
- measure against idle-cash (~0) and `total_pnl` after reseeds
- iterate until evidence shows sustained growth, or report failure honestly

Does **not** unlock live trading. Does **not** authorize leverage, shorts, or fabricated P/L.

## Objective

Beat idle cash on the Founder Learning Desk by:

1. Sitting when the desk + day lose to doing nothing (`sit_in_cash_vs_hodl`)
2. Skipping strategies that lose to cash after ≥5 trades
3. Sizing by **growth lane** × **expectancy** (not a flat ⅓ equity forever)
4. Tightening concurrent opens while protecting / recovering

## Control surfaces

| Input | Effect |
| --- | --- |
| `organic_growth_pace` lane | Size fraction + max opens |
| Strategy expectancy after costs | Size multiplier; hard skip if ≤ 0 with sample |
| Cash reserve (≥40% / $100 floor) | Hard ceiling on deployable cash |
| Desk sit vs cash | Blocks new entries on red underwater days |

## Success criteria (evidence)

1. Primary: `total_pnl` after reseeds > 0 with ≥20 closed paper trades
2. Cash benchmark: do not dig deeper than idle cash on red days
3. Liquidity: keep free-cash target intact
4. Audit: every EGA size/filter decision emits a reason code

## Scorecard

`GET` paper training scorecard includes `equity_growth_algorithm` with version, owner, lane, base notional, and success criteria copy.
