# ADR-017: Durable operating-mode idempotency

- Status: Accepted
- Date: 2026-07-17
- Deciders: Founder (Phase 7)

## Context

Mode transitions are institutional decisions and must survive retries and process restarts without duplicate history.

## Decision

Persist idempotency in `operating_mode_idempotency`:

- Store SHA-256 of the client `Idempotency-Key`
- Store a deterministic request fingerprint
- Store the committed response payload and history reference

Same key + fingerprint replays the original result. Same key + different fingerprint returns `idempotency_conflict`.

## Consequences

- Memory-only caches are insufficient.
- Replay must not append duplicate history or imply a second commit.
- Keys themselves are never stored in plaintext.
