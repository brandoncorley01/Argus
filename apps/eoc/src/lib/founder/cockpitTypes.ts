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
  /** True when symbol came from Coinbase dynamic discovery (not core desk). */
  discovered?: boolean;
  discovery_source?: string | null;
  opportunity_class?: string | null;
  /** Freshly promoted this discovery cycle. */
  newly_discovered?: boolean;
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
  monitor_status?: string;
  outlook: string;
  confidence: string;
  score: number;
  why: string;
  waiting_for: string;
  narrative: string;
  primary_reason?: string;
  watching_since: string;
  watched_seconds: number;
  expires_at: string;
  expire_in_seconds: number;
  next_eval_at: string | null;
  next_eval_in_seconds: number | null;
  current_price: string | null;
  entry_zone: string | null;
  entry_zone_display?: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  risk_reward: number | string | null;
  expected_net_edge_usd?: string | null;
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
  strategy_label?: string;
  micro_subtype?: string | null;
  market_regime?: string | null;
  risk_status: string;
  reason_code: string | null;
  market_data_at: string | null;
  evaluated_at: string;
};

export type CockpitMonitorRow = {
  symbol: string;
  status: string;
  phase: string;
  price: number | null;
  pct_change: number | null;
  outlook: string;
  signal_strength: number;
  timeframe: string | null;
  stale: boolean;
  market_data_at: string | null;
  age_seconds: number | null;
  last_analyzed_at: string | null;
  analyzed_age_seconds: number | null;
  focus: boolean;
};

export type StrategyActivity = {
  window?: string;
  markets_scanned: number;
  strategies_running: number;
  strategies_enabled?: string[];
  setups_found: number;
  watching: number;
  ready: number;
  avoided?: number;
  positions_open: number;
  trades_closed: number;
  realized_net_pnl: string;
  paper_equity: string | null;
  by_strategy?: Record<
    string,
    {
      evaluations?: number;
      watching?: number;
      ready?: number;
      avoided?: number;
      entered?: number;
    }
  >;
  micro_keys?: string[];
  micro_status?: {
    state: "worker_unhealthy" | "position_open" | "cash_reserve" | "watching" | "scanning";
    worker_health: string;
    last_heartbeat: string | null;
    watching: number;
    watching_by_strategy?: Record<string, number>;
    position_count: number;
    position_symbols: string[];
    cash_available: string | null;
    cash_reserve_target: string | null;
    available_notional: string;
    why: string;
    paper_only: boolean;
  };
  last_scan_at?: string | null;
  paper_only?: boolean;
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
  open_position_symbols?: string[];
  focus_symbols?: string[];
  market_data_at: string | null;
  market_data_stale: boolean;
  market_data_age_seconds: number | null;
  trading_allowed: boolean;
  pause_new_entries_active: boolean;
  kill_switch_active: boolean;
  next_step: string | null;
  wall: CockpitWallTile[];
  watches: CockpitWatch[];
  strategy_activity?: StrategyActivity | null;
  monitor?: CockpitMonitorRow[];
  doing: Array<{ text: string; tone: string }>;
  decided: Array<{
    id: string;
    at: string;
    text: string;
    tone: string;
    symbol?: string | null;
  }>;
  rejection_summary?: Array<{ code: string; count: number; why: string }>;
  rejected_live?: Array<{
    symbol: string;
    stage: string;
    reason_code: string | null;
    why: string;
    evaluated_at: string | null;
  }>;
  last_cycle_completed_at?: string | null;
  scan_interval_seconds: number;
  watch_ttl_seconds: number;
  market_discovery?: {
    markets_scanned?: number;
    stats_probed?: number | null;
    active_opportunities?: number;
    active_opportunity_rows?: Array<{
      symbol?: string;
      opportunity_class?: string;
      primary_reason?: string;
      change_pct?: string;
    }>;
    newly_discovered?: Array<
      | string
      | {
          symbol?: string;
          opportunity_class?: string;
          primary_reason?: string;
        }
    >;
    promoted_to_radar?: string[];
    rejected_count?: number;
    rejected_sample?: Array<{
      symbol?: string;
      primary_reason?: string;
      reason?: string;
      opportunity_class?: string;
    }>;
    generated_at?: string | null;
    paper_only?: boolean;
  } | null;
};
