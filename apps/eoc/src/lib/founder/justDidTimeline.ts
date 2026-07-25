/** Server-safe builder for the Home “What Argus just did” timeline. */

import { plainRejection } from "@/lib/founder/plainLanguage";

export type TimelineItem = {
  id: string;
  at: string;
  text: string;
  advanced?: string;
};

export function buildJustDidTimeline(input: {
  scanEvents: Array<{
    id: string;
    occurred_at: string;
    symbol: string | null;
    title: string;
    detail: string;
    outcome: string;
    reason_code: string | null;
    component: string;
    strategy_key: string | null;
    correlation_id: string;
  }>;
  fills: Array<{
    id: string;
    symbol: string;
    side: string;
    quantity: string;
    price: string;
    filled_at: string;
  }>;
  limit?: number;
}): TimelineItem[] {
  const limit = input.limit ?? 12;
  const items: TimelineItem[] = [];

  for (const e of input.scanEvents) {
    const sym = e.symbol ? `${e.symbol}` : "markets";
    let text = e.title;
    if (e.outcome === "rejected") {
      text = `Rejected ${sym} because ${plainRejection(e.reason_code, e.detail)
        .replace(/\.$/, "")
        .toLowerCase()}.`;
    } else if (e.component === "market_scanner") {
      text = e.symbol ? `Scanned ${e.symbol}.` : e.title;
    } else if (e.outcome === "watching") {
      text = `Added ${sym} to the watchlist.`;
    } else if (e.title.toLowerCase().includes("scanning")) {
      text = e.symbol ? `Began analyzing ${e.symbol}.` : e.title;
    }
    items.push({
      id: e.id,
      at: e.occurred_at,
      text,
      advanced: JSON.stringify(
        {
          component: e.component,
          outcome: e.outcome,
          reason_code: e.reason_code,
          strategy_key: e.strategy_key,
          correlation_id: e.correlation_id,
          detail: e.detail,
        },
        null,
        2,
      ),
    });
  }

  for (const f of input.fills) {
    const notional = (Number(f.quantity) * Number(f.price)).toFixed(2);
    items.push({
      id: `fill-${f.id}`,
      at: f.filled_at,
      text: `Opened a $${notional} simulated ${f.symbol} trade (${f.side}).`,
      advanced: JSON.stringify(f, null, 2),
    });
  }

  return items
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at))
    .slice(0, limit);
}
