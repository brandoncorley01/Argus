import { NextRequest, NextResponse } from "next/server";

import { sumTodayRealizedPnl } from "@/lib/founder/todayPnl";
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
  starting_cash?: string;
  net_vs_starting_cash?: string;
  fill_count?: number;
  order_count?: number;
  capital_explanation?: string;
};

type ClosedTrade = {
  fill_id: string;
  symbol: string;
  realized_pnl: string;
  filled_at: string;
};

type PositionSummary = {
  id: string;
  symbol: string;
  quantity: string;
  side: string;
  average_cost: string;
  committed_capital: string;
  market_value?: string | null;
  realized_pnl: string;
  unrealized_pnl: string | null;
  mark_price: string | null;
  pnl_percent: string | null;
  price_status?: string;
  opened_at: string | null;
  strategy_version_id: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  state: string;
};

type TrainingSettings = {
  mode: "automatic" | "coaching";
  default_notional: string;
};

/**
 * Single Home pulse — capital + full open positions + today's Eastern P&L.
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
    const pulseMs = 10_000;
    const [summary, closed, settings, positions] = await Promise.all([
      apiFetch<PortfolioSummary>(
        `/api/v1/paper/portfolios/${portfolioId}/summary`,
        { timeoutMs: pulseMs },
      ),
      apiFetch<ClosedTrade[]>(
        `/api/v1/paper/portfolios/${portfolioId}/closed-trades`,
        { searchParams: { limit: 200 }, timeoutMs: pulseMs },
      ),
      apiFetch<TrainingSettings>(
        `/api/v1/paper/training/${portfolioId}/settings`,
        { timeoutMs: pulseMs },
      ),
      apiFetch<PositionSummary[]>(
        `/api/v1/paper/portfolios/${portfolioId}/position-summaries`,
        { timeoutMs: pulseMs },
      ),
    ]);
    const today = sumTodayRealizedPnl(closed);
    const openUnrealized = positions.reduce((sum, p) => {
      const n = Number(p.unrealized_pnl);
      return sum + (Number.isFinite(n) ? n : 0);
    }, 0);
    return NextResponse.json({
      fetched_at: new Date().toISOString(),
      summary,
      closed_trade_count: today.count,
      recent_closed: closed.slice(0, 5),
      /** Realized P&L for the Eastern calendar day (12 AM → 12 AM). */
      today_realized_pnl: String(today.pnl),
      today_day_key: today.dayKey,
      today_closed_trade_count: today.count,
      /** Backward-compatible alias used by Live Desk closed P&L dial. */
      total_realized_pnl: String(today.pnl),
      open_unrealized_pnl: String(openUnrealized),
      positions,
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
