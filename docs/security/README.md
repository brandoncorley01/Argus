# Security documentation

Secrets, credentials, and personal financial data must never enter Git.

See:

- [`../ARGUS_HEADQUARTERS.md`](../ARGUS_HEADQUARTERS.md) — repository vs runtime boundary
- [`../../.env.example`](../../.env.example) — variable names only
- [`../operations/CREDENTIAL_COMPROMISE.md`](../operations/CREDENTIAL_COMPROMISE.md) — compromise runbook
- ADR-012 secret detection for versioned payloads

Live broker credentials are **out of scope** for current paper operation.
