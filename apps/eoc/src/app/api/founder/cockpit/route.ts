import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/server/api";
import type { CockpitSnapshot } from "@/lib/founder/cockpitTypes";

export const dynamic = "force-dynamic";

export async function GET(req: Request) {
  try {
    const url = new URL(req.url);
    const portfolioId = url.searchParams.get("portfolioId");
    const data = await apiFetch<CockpitSnapshot>("/api/v1/market/scan/cockpit", {
      searchParams: portfolioId ? { portfolio_id: portfolioId } : undefined,
      timeoutMs: 45_000,
    });
    return NextResponse.json(data);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Cockpit unavailable";
    return NextResponse.json(
      { error: message },
      { status: 502 },
    );
  }
}
