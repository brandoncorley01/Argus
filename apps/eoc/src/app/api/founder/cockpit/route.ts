import { NextResponse } from "next/server";

import { apiFetch } from "@/lib/server/api";
import type { CockpitSnapshot } from "@/lib/founder/cockpitTypes";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const data = await apiFetch<CockpitSnapshot>("/api/v1/market/scan/cockpit");
    return NextResponse.json(data);
  } catch (err) {
    const message = err instanceof Error ? err.message : "Cockpit unavailable";
    return NextResponse.json(
      { error: message },
      { status: 502 },
    );
  }
}
