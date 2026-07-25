import { NextResponse } from "next/server";

import { buildDecisionStream } from "@/lib/founder/decisionStream";
import { apiFetch } from "@/lib/server/api";
import { soft } from "@/lib/server/control-plane";

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

type Portfolio = { id: string };
type Fill = {
  id: string;
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  filled_at: string;
};

export async function GET() {
  try {
    const [events, portfolios] = await Promise.all([
      soft(() =>
        apiFetch<ScanEvent[]>("/api/v1/market/scan/events", {
          searchParams: { limit: 40 },
        }),
      ),
      soft(() => apiFetch<Portfolio[]>("/api/v1/paper/portfolios")),
    ]);
    const portfolio = portfolios?.[0] ?? null;
    const fills = portfolio
      ? await soft(() =>
          apiFetch<Fill[]>(`/api/v1/paper/portfolios/${portfolio.id}/fills`),
        )
      : [];
    const items = buildDecisionStream({
      scanEvents: events ?? [],
      fills: (fills ?? []).slice(0, 12),
      limit: 25,
    });
    return NextResponse.json({ items, generated_at: new Date().toISOString() });
  } catch (err) {
    const message = err instanceof Error ? err.message : "decisions_unavailable";
    return NextResponse.json({ items: [], error: message }, { status: 200 });
  }
}
