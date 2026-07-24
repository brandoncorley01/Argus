# ADR-028: Execution Gateway and Internal Paper Provider

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder

## Context

Phase 12 requires end-to-end simulated trading without external financial accounts. Future brokers must plug in without coupling strategies to vendor APIs.

## Decision

- Introduce a broker-agnostic `ExecutionProvider` contract and `ExecutionGateway`.
- Default provider: `internal_paper` (paper environment).
- Secondary: `deterministic_test` for fixtures.
- Live/broker adapters are out of scope and cannot be selected as default.
- Strategies and portfolios interact only through the gateway.

## Consequences

- Platform is fully usable offline with local Postgres/Redis.
- Capability declarations allow safe failure for unsupported operations.
- No credentials or identity documents required for Phase 12 certification.
