"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import type { PositionSummary } from "@/components/founder/ActiveTrades";

const POLL_MS = 4_000;
/** Wall-clock jump above this (tab backgrounded / host sleep) forces an immediate pulse. */
const WAKE_GAP_MS = 8_000;

export type PaperLiveAccount = {
  balance: string | null;
  cash: string | null;
  inTrades: string | null;
  openCount: number;
  startingCash?: string | null;
  netVsStart?: string | null;
  fillCount?: number | null;
  capitalExplanation?: string | null;
};

export type PaperLivePulse = {
  fetchedAt: string | null;
  account: PaperLiveAccount;
  positions: PositionSummary[];
  totalRealizedPnl: number | null;
  openUnrealizedPnl: number | null;
  closedTradeCount: number;
  mode: "automatic" | "coaching" | null;
};

type PaperLiveContextValue = PaperLivePulse & {
  portfolioId: string | null;
  refreshing: boolean;
};

const PaperLiveContext = createContext<PaperLiveContextValue | null>(null);

type PulseResponse = {
  fetched_at?: string;
  summary: {
    total_account_value: string;
    cash_balance: string;
    buying_power: string;
    committed_capital: string;
    open_position_count: number;
    starting_cash?: string;
    net_vs_starting_cash?: string;
    fill_count?: number;
    capital_explanation?: string;
  };
  positions?: PositionSummary[];
  open_positions?: Array<{
    symbol: string;
    unrealized_pnl: string | null;
    mark_price: string | null;
    stop_loss: string | null;
    take_profit: string | null;
  }>;
  total_realized_pnl?: string;
  today_realized_pnl?: string;
  today_day_key?: string;
  today_closed_trade_count?: number;
  open_unrealized_pnl?: string;
  closed_trade_count?: number;
  mode?: "automatic" | "coaching";
};

function seedPulse(
  account: PaperLiveAccount,
  positions: PositionSummary[],
  totalPnl: number | null,
  mode: "automatic" | "coaching" | null,
): PaperLivePulse {
  return {
    fetchedAt: null,
    account,
    positions,
    totalRealizedPnl: totalPnl,
    openUnrealizedPnl: null,
    closedTradeCount: 0,
    mode,
  };
}

export function PaperLiveProvider({
  portfolioId,
  seedAccount,
  seedPositions,
  seedTotalPnl,
  seedMode = null,
  children,
}: {
  portfolioId: string | null;
  seedAccount: PaperLiveAccount;
  seedPositions: PositionSummary[];
  seedTotalPnl: number | null;
  seedMode?: "automatic" | "coaching" | null;
  children: ReactNode;
}) {
  const [pulse, setPulse] = useState<PaperLivePulse>(() =>
    seedPulse(seedAccount, seedPositions, seedTotalPnl, seedMode),
  );
  const [refreshing, setRefreshing] = useState(false);

  const applyPulse = useCallback((data: PulseResponse) => {
    const positions =
      data.positions && data.positions.length > 0
        ? data.positions
        : (data.open_positions ?? []).map((p, i) => ({
            id: `live-${p.symbol}-${i}`,
            symbol: p.symbol,
            quantity: "0",
            side: "long",
            average_cost: "0",
            committed_capital: "0",
            realized_pnl: "0",
            unrealized_pnl: p.unrealized_pnl,
            mark_price: p.mark_price,
            pnl_percent: null,
            opened_at: null,
            strategy_version_id: null,
            stop_loss: p.stop_loss,
            take_profit: p.take_profit,
            state: "open",
          }));

    setPulse({
      fetchedAt: data.fetched_at ?? new Date().toISOString(),
      account: {
        balance: data.summary.total_account_value,
        // True remaining paper cash (not buying_power). Equity = cash + marks.
        cash: data.summary.cash_balance,
        inTrades: data.summary.committed_capital,
        openCount: data.summary.open_position_count,
        startingCash: data.summary.starting_cash ?? null,
        netVsStart: data.summary.net_vs_starting_cash ?? null,
        fillCount: data.summary.fill_count ?? null,
        capitalExplanation: data.summary.capital_explanation ?? null,
      },
      positions,
      totalRealizedPnl:
        data.today_realized_pnl != null
          ? Number(data.today_realized_pnl)
          : data.total_realized_pnl != null
            ? Number(data.total_realized_pnl)
            : null,
      openUnrealizedPnl:
        data.open_unrealized_pnl != null
          ? Number(data.open_unrealized_pnl)
          : null,
      closedTradeCount:
        data.today_closed_trade_count ?? data.closed_trade_count ?? 0,
      mode: data.mode ?? null,
    });
  }, []);

  useEffect(() => {
    if (!portfolioId) return;
    let cancelled = false;
    let inFlight = false;
    let lastTick = Date.now();

    const poll = async () => {
      if (inFlight) return;
      inFlight = true;
      if (!cancelled) setRefreshing(true);
      try {
        const res = await fetch(
          `/api/founder/paper-pulse?portfolioId=${encodeURIComponent(portfolioId)}`,
          { cache: "no-store", signal: AbortSignal.timeout(12_000) },
        );
        if (!res.ok) return;
        const data = (await res.json()) as PulseResponse;
        if (cancelled || !data.summary) return;
        applyPulse(data);
      } catch {
        /* keep last good pulse */
      } finally {
        inFlight = false;
        lastTick = Date.now();
        if (!cancelled) setRefreshing(false);
      }
    };

    void poll();
    const id = window.setInterval(() => {
      const gap = Date.now() - lastTick;
      void poll();
      // Detect host sleep / long background: interval may fire late after wake.
      if (gap > WAKE_GAP_MS + POLL_MS) {
        void poll();
      }
    }, POLL_MS);

    const onVisible = () => {
      if (document.visibilityState === "visible") void poll();
    };
    document.addEventListener("visibilitychange", onVisible);

    return () => {
      cancelled = true;
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [portfolioId, applyPulse]);

  const value = useMemo<PaperLiveContextValue>(
    () => ({
      ...pulse,
      portfolioId,
      refreshing,
    }),
    [pulse, portfolioId, refreshing],
  );

  return (
    <PaperLiveContext.Provider value={value}>{children}</PaperLiveContext.Provider>
  );
}

export function usePaperLive(): PaperLiveContextValue {
  const ctx = useContext(PaperLiveContext);
  if (!ctx) {
    throw new Error("usePaperLive must be used inside PaperLiveProvider");
  }
  return ctx;
}

/** Optional — components that also work outside the provider. */
export function usePaperLiveOptional(): PaperLiveContextValue | null {
  return useContext(PaperLiveContext);
}
