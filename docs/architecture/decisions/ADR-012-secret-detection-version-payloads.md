# ADR-012: Secret detection for versioned payloads

- Status: Accepted
- Date: 2026-07-16
- Deciders: Founder (Phase 6 defaults)

## Context

Configuration and policy JSON is durable and auditable. Accidentally storing credentials would create a permanent secret leak in the system of record.

## Decision

1. Reject payloads whose keys match credential-like names (`password`, `api_key`, `token`, `secret`, etc.).
2. Reject string values matching common secret material patterns (PEM private keys, live API key prefixes).
3. Perform detection before hash persistence and before draft updates.

## Consequences

- Legitimate non-secret fields must avoid forbidden key names.
- Detection is heuristic, not a substitute for operational secret management outside versioned documents.
