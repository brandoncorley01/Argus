/** Founder-readable decision stream from scan events + paper fills. */

export type DecisionItem = {
  id: string;
  at: string;
  symbol: string | null;
  event: string;
  outcome: string;
  reason: string;
  strategy: string | null;
  correlationId: string | null;
  tone: "info" | "ok" | "warn" | "bad";
};

type ScanEvent = {
  id: string;
  occurred_at: string;
  symbol: string | null;
  title: string;
  detail: string;
  outcome: string;
  reason_code: string | null;
  strategy_key: string | null;
  correlation_id: string;
  component: string;
};

type FillLike = {
  id?: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  filled_at: string;
};

function toneFor(outcome: string): DecisionItem["tone"] {
  const o = outcome.toLowerCase();
  if (o.includes("reject") || o.includes("fail") || o.includes("block")) return "bad";
  if (o.includes("warn") || o.includes("stale") || o.includes("pause")) return "warn";
  if (o.includes("complete") || o.includes("watching") || o.includes("pass")) return "ok";
  return "info";
}

export function buildDecisionStream(opts: {
  scanEvents?: ScanEvent[] | null;
  fills?: FillLike[] | null;
  limit?: number;
}): DecisionItem[] {
  const items: DecisionItem[] = [];

  for (const e of opts.scanEvents ?? []) {
    // Prefer market/strategy events; skip empty titles.
    if (!e.title) continue;
    items.push({
      id: `scan-${e.id}`,
      at: e.occurred_at,
      symbol: e.symbol,
      event: e.title,
      outcome: e.outcome,
      reason: e.detail || e.reason_code || "",
      strategy: e.strategy_key,
      correlationId: e.correlation_id,
      tone: toneFor(e.outcome),
    });
  }

  for (const f of opts.fills ?? []) {
    const opened = f.side === "buy";
    items.push({
      id: `fill-${f.id ?? `${f.symbol}-${f.filled_at}`}`,
      at: f.filled_at,
      symbol: f.symbol,
      event: opened ? "Position opened / increased" : "Position reduced / closed",
      outcome: opened ? "entered" : "closed",
      reason: `${f.side} ${f.quantity} @ ${f.price}`,
      strategy: null,
      correlationId: null,
      tone: opened ? "ok" : "info",
    });
  }

  items.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));
  const limit = opts.limit ?? 25;
  return items.slice(0, limit);
}

export const REJECTION_LABELS: Record<string, string> = {
  weak_signal: "Weak signal",
  confirmation_incomplete: "Confirmation incomplete",
  low_liquidity: "Low liquidity",
  excessive_volatility: "Excessive volatility",
  poor_risk_reward: "Poor risk/reward",
  exposure_limit: "Exposure limit",
  daily_risk_limit: "Daily risk limit / entries paused",
  stale_data: "Stale data",
  execution_unavailable: "Execution unavailable",
  no_instruments: "No instruments registered",
  pause_new_entries: "New entries paused",
};
