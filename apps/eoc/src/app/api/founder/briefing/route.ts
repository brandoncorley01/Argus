import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/server/api";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type BriefingPayload = Record<string, unknown>;

/**
 * BFF proxy for Executive Briefing. Home polls this path; a missing route
 * 404s forever and the panel stays on "loading…".
 */
export async function GET() {
  try {
    const data = await apiFetch<BriefingPayload>(
      "/api/v1/operations/trading-intelligence/briefing",
      { timeoutMs: 20_000 },
    );
    return NextResponse.json(data, {
      headers: { "Cache-Control": "no-store" },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Briefing unavailable";
    return NextResponse.json(
      {
        error: message,
        bullets: [
          "Average confidence: —",
          "Best strategy today: —",
          "Largest risk: —",
          "Largest missed opportunity: —",
          "Recommendation: Start Argus if the control plane is down",
        ],
        trading_intelligence_summary: [
          "Executive Briefing could not reach the API. Paper trading may still be running.",
        ],
        founder_action_required: "Confirm Argus is Running, then reload Home.",
        live_trading_locked: true,
        mode: "PROVE",
      },
      { status: 200, headers: { "Cache-Control": "no-store" } },
    );
  }
}
