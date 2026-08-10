import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/server/api";

export const dynamic = "force-dynamic";

/** Proxies Argus Academy advanced-learning pane (can exceed default API timeout). */
export async function GET(req: NextRequest) {
  const portfolioId = req.nextUrl.searchParams.get("portfolioId");
  if (!portfolioId) {
    return NextResponse.json(
      { error: "portfolioId is required" },
      { status: 400 },
    );
  }
  try {
    const pane = await apiFetch<Record<string, unknown>>(
      `/api/v1/paper/training/${portfolioId}/advanced-learning`,
      { timeoutMs: 45_000 },
    );
    return NextResponse.json(pane ?? { error: "Academy pane empty" });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Academy unavailable";
    return NextResponse.json(
      {
        error: message.slice(0, 200),
        live_trading_enabled: false,
        learning_day: 1,
        required_days: 20,
        disclaimer:
          "Argus Academy is temporarily unavailable — retry in a moment while Argus stays Running.",
      },
      { status: 200 },
    );
  }
}
