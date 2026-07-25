import { NextResponse } from "next/server";

import { buildFounderActivity } from "@/lib/founder/activityFeed";
import { apiFetch } from "@/lib/server/api";
import { getAuditEvents, soft } from "@/lib/server/control-plane";

type OpsEvent = {
  id: string;
  occurred_at: string;
  component: string;
  severity: string;
  description: string;
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
    const [audits, ops, portfolios] = await Promise.all([
      soft(() => getAuditEvents({ limit: 30 })),
      soft(() =>
        apiFetch<OpsEvent[]>("/api/v1/operations/events", {
          searchParams: { limit: 30 },
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

    const items = buildFounderActivity({
      audits: audits?.items ?? [],
      ops: ops ?? [],
      fills: (fills ?? []).slice(0, 12),
      limit: 20,
    });
    return NextResponse.json({ items, generated_at: new Date().toISOString() });
  } catch (err) {
    const message = err instanceof Error ? err.message : "activity_unavailable";
    return NextResponse.json({ items: [], error: message }, { status: 200 });
  }
}
