/**
 * Founder milestone strip — aligned to ROADMAP.md (do not invent P&L or strategy claims).
 * Phases 0–15 Done/Verified; Phase 16 Planned. Sprint 5 = Founder RC1 operating package.
 */
export const FOUNDER_MILESTONE = {
  id: "founder-rc1",
  label: "Founder Release Candidate (RC1)",
  sprint: "Sprint 5",
  phasesComplete: 15,
  phasesTotal: 16,
  provider: "internal_paper",
  liveTrading: "Disabled",
  note: "Phases 0–15 complete per ROADMAP. Phase 16 (hardening & CI follow-ups) planned. Live trading remains deny-by-default.",
} as const;

export function milestoneProgressPercent(): number {
  const { phasesComplete, phasesTotal } = FOUNDER_MILESTONE;
  if (phasesTotal <= 0) return 0;
  return Math.round((phasesComplete / phasesTotal) * 100);
}
