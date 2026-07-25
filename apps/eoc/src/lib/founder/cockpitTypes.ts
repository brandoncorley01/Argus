/** Types for the Live Trading Cockpit (genuine scan/market data). */

export type CockpitWallTile = {
  symbol: string;
  current_price: number | null;
  pct_change: number | null;
  sparkline: number[];
  outlook: string;
  signal_strength: number;
  status: string;
  last_analyzed_at: string | null;
  candidate_id: string | null;
  timeframe: string | null;
  market_data_at: string | null;
  stale: boolean;
};

export type CockpitChecklistItem = {
  key: string;
  label: string;
  status: "passed" | "waiting" | "failed" | string;
};

export type CockpitWatch = {
  id: string;
  symbol: string;
  stage_raw: string;
  outlook: string;
  confidence: string;
  score: number;
  why: string;
  waiting_for: string;
  narrative: string;
  watching_since: string;
  watched_seconds: number;
  expires_at: string;
  expire_in_seconds: number;
  next_eval_at: string | null;
  next_eval_in_seconds: number | null;
  current_price: string | null;
  entry_zone: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  risk_reward: number | null;
  paper_capital_planned: string;
  max_dollar_loss: string | null;
  potential_dollar_profit: string | null;
  checklist: CockpitChecklistItem[];
  checklist_waiting: number;
  checklist_summary: string;
  support: number | null;
  resistance: number | null;
  timeframe: string;
  strategy_key: string;
  risk_status: string;
  reason_code: string | null;
  market_data_at: string | null;
  evaluated_at: string;
};

export type CockpitSnapshot = {
  generated_at: string;
  headline: string | null;
  scanner_state: string;
  current_market: string | null;
  markets_monitored: number;
  scan_progress: { scanned: number; total: number };
  next_scan_at: string | null;
  possible_trades_found: number;
  watching_count: number;
  awaiting_confirmation: number;
  risk_check_count: number;
  open_trades: number;
  market_data_at: string | null;
  market_data_stale: boolean;
  market_data_age_seconds: number | null;
  trading_allowed: boolean;
  pause_new_entries_active: boolean;
  kill_switch_active: boolean;
  next_step: string | null;
  wall: CockpitWallTile[];
  watches: CockpitWatch[];
  doing: Array<{ text: string; tone: string }>;
  decided: Array<{ id: string; at: string; text: string; tone: string }>;
  scan_interval_seconds: number;
  watch_ttl_seconds: number;
};
