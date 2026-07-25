import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/server/api";
import { soft } from "@/lib/server/control-plane";

type BarsResponse = {
  symbol: string;
  timeframe: string | null;
  available: boolean;
  bars: Array<{
    open_time: string;
    close_time: string;
    open: string;
    high: string;
    low: string;
    close: string;
    volume: string | null;
  }>;
};

export async function GET(req: NextRequest) {
  const symbol = req.nextUrl.searchParams.get("symbol");
  if (!symbol) {
    return NextResponse.json(
      { available: false, bars: [], error: "symbol_required" },
      { status: 200 },
    );
  }
  const data = await soft(() =>
    apiFetch<BarsResponse>(`/api/v1/market/scan/bars/${encodeURIComponent(symbol)}`, {
      searchParams: { limit: 60 },
    }),
  );
  if (!data) {
    return NextResponse.json({ available: false, bars: [], timeframe: null }, { status: 200 });
  }
  return NextResponse.json(data);
}
