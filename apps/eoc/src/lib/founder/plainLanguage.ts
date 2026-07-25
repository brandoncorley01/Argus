/** Founder-facing plain-language helpers (mirrors API plain_language.py). */

export const REJECTION_PLAIN: Record<string, string> = {
  insufficient_history:
    "There is not enough recent price history to evaluate this strategy safely.",
  stale_data:
    "Market prices are too old. Argus will not open a trade until prices refresh.",
  low_liquidity: "Recent trading volume is too low for a safe entry.",
  weak_signal: "The move is not strong enough to meet Argus entry rules.",
  confirmation_incomplete:
    "Argus is waiting for more confirmation before entering.",
  excessive_volatility: "Price swings are too large for the allowed risk.",
  poor_risk_reward:
    "The possible reward is too small compared with the risk.",
  exposure_limit: "This would put too much paper money into one area.",
  daily_risk_limit: "Daily paper risk limits are reached.",
  pause_new_entries: "New paper entries are paused by the Founder.",
  execution_unavailable:
    "Paper trading is blocked (kill switch or execution unavailable).",
  no_instruments: "No markets are registered for scanning yet.",
};

export function plainRejection(
  code: string | null | undefined,
  fallback?: string | null,
): string {
  if (code && REJECTION_PLAIN[code]) return REJECTION_PLAIN[code];
  if (fallback) return fallback;
  return "Argus decided not to take this setup.";
}

export function confidenceFromScore(score: number): "Low" | "Medium" | "High" {
  if (score >= 80) return "High";
  if (score >= 50) return "Medium";
  return "Low";
}

export function outlookLabel(bias: string): string {
  if (bias === "Bullish") return "Price may rise";
  if (bias === "Bearish") return "Price may fall";
  return "No clear direction";
}

export function decisionLabel(stage: string): string {
  if (stage === "Watching" || stage === "Evaluating") return "Watching";
  if (stage === "Risk Review" || stage === "Approved" || stage === "Entered")
    return "Ready";
  if (stage === "Expired") return "Expired";
  return "Rejected";
}

export const FEEDBACK_OPTIONS = [
  { code: "good_decision", label: "Good decision" },
  { code: "bad_decision", label: "Bad decision" },
  { code: "entered_too_early", label: "Entered too early" },
  { code: "entered_too_late", label: "Entered too late" },
  { code: "exited_too_early", label: "Exited too early" },
  { code: "exited_too_late", label: "Exited too late" },
  { code: "risk_too_high", label: "Risk was too high" },
  { code: "position_too_small", label: "Position was too small" },
  { code: "position_too_large", label: "Position was too large" },
  { code: "agree_rejection", label: "I agree with the rejection" },
  { code: "disagree_rejection", label: "I disagree with the rejection" },
  { code: "personal_note", label: "Personal note" },
] as const;
