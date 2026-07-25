# Market Command Center (Home)

Home (`/today`) is the Founder daily command center. Build id: `paper-training-lab-v1`.

See also: [`PAPER_TRAINING_LAB.md`](./PAPER_TRAINING_LAB.md).

## Five Home questions

1. **What is Argus doing now?** — live statement, scan progress, refresh/scan actions
2. **Your paper account** — balance, cash, money in trades, P&L, open trades (simulated)
3. **Trades Argus is considering** — plain-language candidates
4. **Open paper trades** — cards with stale-price safety
5. **What Argus just did** — short timeline; advanced IDs hidden by default

Primary nav: Home · Paper Training · Trades · Reports · Settings (Advanced for diagnostics).

## Data honesty

- Prices come from public Coinbase Exchange candles via **Refresh recent prices** / worker refresh
- Argus does **not** invent scanner movement or chart activity
- Missing marks → P&L unavailable (never shown as zero)
- Live trading remains locked behind formal authorization
