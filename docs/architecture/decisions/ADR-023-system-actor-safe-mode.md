# ADR-023: SYSTEM actor auto-degrade to SAFE_MODE

- Status: Accepted
- Date: 2026-07-19
- Deciders: Founder

## Context

Critical dependency failure must protect capital without inventing a human session or bypassing the mode state machine.

## Decision

Introduce `OperatingModeService.system_enter_safe_mode`:

- No human principal (`changed_by_user_id` / `actor_user_id` null)
- Audit payload includes `actor: "SYSTEM"`
- Eligible only from OBSERVE / PAPER / MICRO_LIVE / NORMAL_LIVE
- Triggered after N consecutive critical failures (default 3)
- Still uses mode history, idempotency, prerequisites, and fail-closed audit

## Consequences

- Protective degrade is auditable and replay-safe.
- Recovery remains a human Founder action (Phase 7 rules).
- OFF / SAFE_MODE / EMERGENCY_STOP / uninitialized states are not auto-degraded.
