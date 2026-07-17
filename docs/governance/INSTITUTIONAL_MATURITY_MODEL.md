# Institutional Maturity Model

Argus tracks institutional maturity by capability level. Levels describe readiness, not marketing status. Do not claim a higher level without evidence.

## Department capability levels

| Level | Name | Meaning |
| --- | --- | --- |
| 0 | Concept | Intent and constraints documented; no durable runtime capability |
| 1 | Foundation | Control-plane foundations exist (identity, governance, infra, audit posture) |
| 2 | Observe | System can observe and record without execution |
| 3 | Paper | Paper-trading capability validated under controls |
| 4 | Micro Live | Constrained live capability approved and unlocked |
| 5 | Production | Production live operations under full controls |
| 6 | Institutional | Full institutional operating maturity |

## Version 0.1 Foundation target

Argus v0.1 Foundation targets **Level 1 — Foundation** for the control plane and local infrastructure.

| Area | Target level (v0.1) | Notes |
| --- | --- | --- |
| Governance / identity | 1 | Documented identity, ADRs, feature governance |
| Infrastructure (Postgres/Redis) | 1 | Compose foundation; no application schema yet |
| Authentication / audit | 0 → 1 (later phases) | Not implemented in Phase 0/1 |
| Observation / research runtime | 0 | No observe pipeline yet |
| Paper execution | 0 | No trading engine |
| Micro live / production | 0 | Modes locked; forbidden in v0.1 |

## Advancement rules

- Advancement requires Founder approval and supporting evidence.
- Feature Registry status and locks must align with maturity claims.
- `MICRO_LIVE` and `NORMAL_LIVE` remain locked at Level 0 capability for those modes in v0.1.
- Do not display fake maturity gauges or decorative progress UI.
