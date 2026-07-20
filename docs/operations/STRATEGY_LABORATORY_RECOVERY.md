# Strategy Laboratory recovery

## Symptoms

- Research runs stuck in `running`
- Immutable version mutation rejected
- Walk-forward missing OOS metrics

## Checks

1. Migration head includes `d0e1f2a3b4c5`.
2. Dataset `metadata_json.bars` present for sync fixtures.
3. Cancel run via API if `cancel_requested` needed.
4. Confirm strategy_class is in closed registry.
5. Review audit events `strategy.*` / research run actions.

## Boundaries

Do not treat research metrics as live profitability. Do not unlock live execution from the laboratory.
