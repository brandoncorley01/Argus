import { NextRequest, NextResponse } from "next/server";

import { apiFetch } from "@/lib/server/api";

export const dynamic = "force-dynamic";

type PortfolioSummary = {
  portfolio_id: string;
  cash_balance: string;
  reserved_cash: string;
  buying_power: string;
  committed_capital: string;
  total_account_value: string;
  open_position_count: number;
  kill_switch_active: boolean;
  pause_new_entries_active: boolean;
  status: string;
};

type ClosedTrade = {
  fill_id: string;
  symbol: string;
  realized_pnl: string;
  filled_at: string;
};

type PositionSummary = {
  symbol: string;
  unrealized_pnl: string | null;
  mark_price: string | null;
  stop_loss: string | null;
  take_profit: string | null;
};

type TrainingSettings = {
  mode: "automatic" | "coaching";
  default_notional: string;
};

/**
 * Live paper-account pulse for Home dials — genuine portfolio figures only.
 */
export async function GET(req: NextRequest) {
  const portfolioId = req.nextUrl.searchParams.get("portfolioId");
  if (!portfolioId) {
    return NextResponse.json(
      { error: "portfolioId is required" },
      { status: 400 },
    );
  }
  try {
    const [summary, closed, settings, positions] = await Promise.all([
      apiFetch<PortfolioSummary>(
        `/api/v1/paper/portfolios/${portfolioId}/summary`,
      ),
      apiFetch<ClosedTrade[]>(
        `/api/v1/paper/portfolios/${portfolioId}/closed-trades`,
        { searchParams: { limit: 8 } },
      ),
      apiFetch<TrainingSettings>(
        `/api/v1/paper/training/${portfolioId}/settings`,
      ),
      apiFetch<PositionSummary[]>(
        `/api/v1/paper/portfolios/${portfolioId}/position-summaries`,
      ),
    ]);
    const totalPnl = closed.reduce(
      (sum, t) => sum + (Number(t.realized_pnl) || 0),
      0,
    );
    const openUnrealized = positions.reduce((sum, p) => {
      const n = Number(p.unrealized_pnl);
      return sum + (Number.isFinite(n) ? n : 0);
    }, 0);
    return NextResponse.json({
      fetched_at: new Date().toISOString(),
      summary,
      closed_trade_count: closed.length,
      recent_closed: closed.slice(0, 5),
      total_realized_pnl: String(totalPnl),
      open_unrealized_pnl: String(openUnrealized),
      open_positions: positions.map((p) => ({
        symbol: p.symbol,
        unrealized_pnl: p.unrealized_pnl,
        mark_price: p.mark_price,
        stop_loss: p.stop_loss,
        take_profit: p.take_profit,
      })),
      mode: settings.mode,
      default_notional: settings.default_notional,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Paper pulse unavailable";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
