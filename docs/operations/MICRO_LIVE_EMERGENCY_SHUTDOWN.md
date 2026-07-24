# Micro-Live emergency shutdown

Applies to the Phase 13 micro-live subsystem. **In this phase, live execution cannot be active** (`live_activation_state` has no reachable path to `MICRO_LIVE_ACTIVE`), so this runbook documents the control surface for a future phase and the checks to confirm the system is safe today.

## Immediate actions (Founder)

1. Activate the global kill switch:
   `POST /api/v1/micro-live/kill-switches` with `{"scope_type": "global", "active": true, "reason": "<why>"}`.
2. Confirm no live execution is possible regardless:
   `GET /api/v1/micro-live/status` → `live_execution_active` must be `false`, `activation_state` must not be `MICRO_LIVE_ACTIVE` (and cannot be, by construction).
3. Transition `live_activation_state` toward `SUSPENDED` or `EMERGENCY_STOP` via `POST /api/v1/micro-live/activation/transition` if narrowing the activation posture is desired (Founder-only).
4. If the global `OperatingMode` is implicated, use the existing Phase 7 emergency-stop path (`POST /api/v1/operating-mode/emergency-stop`) — this is the authoritative institutional stop and is independent of `live_activation_state`.

## Verification

- `GET /api/v1/micro-live/status` shows `global_kill_switch_active: true`.
- `GET /api/v1/paper/...` confirms paper trading (if desired) is unaffected — paper and live are independent execution paths.
- Audit log contains the kill-switch and any activation transition events with actor and reason.

## Recovery

- Clear the kill switch only after root cause is understood: `POST /api/v1/micro-live/kill-switches` with `active: false`.
- Do not attempt to reach `MICRO_LIVE_ACTIVE` as part of recovery — it is not a valid target in this phase.
