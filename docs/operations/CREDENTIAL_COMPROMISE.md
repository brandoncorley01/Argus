# Credential compromise response

Applies to Phase 13 `credential_references`. Argus never stores a credential value — only a reference to an environment variable name — so "compromise" in this system means the underlying secret (held outside Argus, e.g. in the host environment or secrets manager) may be exposed.

## Immediate actions (Founder)

1. Rotate the credential at the source (exchange/broker console, secrets manager). Argus has no role in rotation — it never held the value.
2. Remove or blank the environment variable referenced by the affected `ref_name` so `is_present_cached` will report `false` on next check.
3. Re-run presence validation: `POST /api/v1/micro-live/credential-references/{id}/validate`. Confirm the response shows `is_present_cached: false` and, as always, no value is returned.
4. Activate a provider-scoped kill switch for the affected `provider_key`:
   `POST /api/v1/micro-live/kill-switches` with `{"scope_type": "provider", "scope_id": "<provider_key>", "active": true, "reason": "credential compromise"}`.
5. If `live_activation_state` had progressed past `CREDENTIAL_REFERENCE_CONFIGURED` (not possible with real live execution in this phase, but the state itself may have advanced), transition back toward `PAPER_ONLY` or `SUSPENDED`.

## Verification

- `GET /api/v1/micro-live/credential-references` shows `is_present_cached: false` for the affected reference.
- `GET /api/v1/micro-live/status` shows `credentials_configured` reflecting the reduced credential set.
- Audit log shows the validate and kill-switch events, with the reference NAME only — never a value.

## Notes

- Because Argus never logs or stores values, "credential compromise" investigations should focus on the external system (host, secrets manager, CI) where the value actually lives.
- Do not paste secret values into Argus forms, tickets, or audit notes referencing this incident.
