# Paper Trading Institution (Phase 12)

## Purpose

Complete internal paper-trading institution with a broker-agnostic Execution Gateway. The **Internal Paper Execution Provider** is the default and authoritative development/certification provider.

No brokerage account, exchange account, SSN, paid API, or real capital is required.

## Architecture

```
Argus Core → Execution Gateway → Internal Paper Provider (default)
                               → Deterministic Test Provider
                               → Testnet stubs (optional, future — not required)
```

Institutional services never call broker APIs directly.

## Safety

- Gateway rejects non-paper environments
- Kill switch at portfolio + gateway
- Short selling forbidden
- Explicit provider/environment/portfolio/strategy_version on orders
- Idempotent submit via `Idempotency-Key`
- Audited mutations

See ADR-028.
