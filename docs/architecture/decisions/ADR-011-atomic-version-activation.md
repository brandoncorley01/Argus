# ADR-011: Atomic configuration and policy activation

- Status: Accepted
- Date: 2026-07-16
- Deciders: Founder (Phase 6 defaults)

## Context

Activating a version must supersede the previous active version without leaving two ACTIVE rows or an unaudited switch.

## Decision

1. Take a row lock on the parent document during activation.
2. Supersede any existing ACTIVE version, activate the approved version, and write audit events in one commit.
3. On mapped policy kinds (`constitution`, `operating`, `governance`, `treasury`, `research`), update the corresponding Institutional Identity string pointer to the activated `version_label`.
4. If audit persistence fails, roll back the entire activation (fail-closed).

## Consequences

- Concurrent activations serialize on the document lock.
- Institutional Identity strings remain synchronized with ACTIVE policy versions for mapped kinds.
- ACTIVE database rows remain the source of truth for runtime lookups.
