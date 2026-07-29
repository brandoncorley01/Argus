"use client";

import { useEffect, useState } from "react";

import { ClearPaperSymbolButton } from "@/components/founder/ClearPaperSymbolButton";
import { EmptyState } from "@/components/ui";
import { money, moneyPnl, pnlClass } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";

export type PositionSummary = {
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

function timeInTrade(openedAt: string | null, nowMs: number): string {
  if (!openedAt) return "Unknown";
  const ms = nowMs - Date.parse(openedAt);
  if (!Number.isFinite(ms) || ms < 0) return "Unknown";
  const mins = Math.floor(ms / 60000);
  if (mins < 60) return `${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours} hr`;
  return `${Math.floor(hours / 24)} days`;
}

function TimeInTradeLabel({ openedAt }: { openedAt: string | null }) {
  const [label, setLabel] = useState("—");
  useEffect(() => {
    const tick = () => setLabel(timeInTrade(openedAt, Date.now()));
    tick();
    const id = window.setInterval(tick, 30_000);
    return () => window.clearInterval(id);
  }, [openedAt]);
  return <>{label}</>;
}

export function ActiveTrades({
  positions,
  portfolioId = null,
}: {
  positions: PositionSummary[];
  portfolioId?: string | null;
}) {
  if (positions.length === 0) {
    return (
      <EmptyState>
        No open paper trades. When Argus enters a simulated trade, it will show
        here with entry, stop, target, and profit or loss.
      </EmptyState>
    );
  }

  return (
    <div className="open-trade-cards">
      {positions.map((p) => {
        const entry = Number(p.average_cost);
        const mark = p.mark_price != null ? Number(p.mark_price) : null;
        const absurdEntry =
          (p.symbol.toUpperCase().startsWith("BTC") && entry > 0 && entry < 1000) ||
          (p.symbol.toUpperCase().startsWith("ETH") && entry > 0 && entry < 50);
        const stale =
          p.price_status === "unavailable" ||
          p.mark_price == null ||
          p.unrealized_pnl == null ||
          absurdEntry;
        const stop = p.stop_loss != null ? Number(p.stop_loss) : null;
        const target = p.take_profit != null ? Number(p.take_profit) : null;
        const isLong = p.side === "long" || Number(p.quantity) > 0;
        const stopBreached =
          !stale &&
          mark != null &&
          stop != null &&
          Number.isFinite(mark) &&
          Number.isFinite(stop) &&
          (isLong ? mark <= stop : mark >= stop);
        const targetHit =
          !stale &&
          !stopBreached &&
          mark != null &&
          target != null &&
          Number.isFinite(mark) &&
          Number.isFinite(target) &&
          (isLong ? mark >= target : mark <= target);
        const boughtOrSold =
          isLong ? "Bought" : "Sold";
        return (
          <article key={p.id} className="open-trade-card">
            <header className="open-trade-head">
              <h3>{p.symbol}</h3>
              <span className="muted-note">{boughtOrSold}</span>
            </header>
            {absurdEntry ? (
              <p className="attention-box" role="status">
                This paper entry looks inaccurate (test/stale price{" "}
                {money(p.average_cost)}
                {mark != null ? `, mark ${money(String(mark))}` : ""}). Remove it
                and refresh recent prices so Argus can restart with real market
                data.
              </p>
            ) : null}
            <dl className="considering-dl">
              <div>
                <dt>Entry price</dt>
                <dd>{money(p.average_cost)}</dd>
              </div>
              <div>
                <dt>Current price</dt>
                <dd>
                  {stale
                    ? "Outdated"
                    : p.mark_price
                      ? money(p.mark_price)
                      : "Unavailable"}
                </dd>
              </div>
              <div>
                <dt>Paper money invested</dt>
                <dd>{money(p.committed_capital)}</dd>
              </div>
              <div>
                <dt>Current profit or loss</dt>
                <dd>
                  {stale ? (
                    <span className="warn-text">Cannot calculate safely</span>
                  ) : (
                    <span className={pnlClass(p.unrealized_pnl)}>
                      {moneyPnl(p.unrealized_pnl)}
                      {p.pnl_percent != null
                        ? ` (${Number(p.pnl_percent).toFixed(2)}%)`
                        : ""}
                    </span>
                  )}
                </dd>
              </div>
              <div>
                <dt>Stop-loss</dt>
                <dd>{p.stop_loss ? money(p.stop_loss) : "Not set"}</dd>
              </div>
              <div>
                <dt>Profit target</dt>
                <dd>{p.take_profit ? money(p.take_profit) : "Not set"}</dd>
              </div>
              <div>
                <dt>Time in trade</dt>
                <dd>
                  <TimeInTradeLabel openedAt={p.opened_at} />
                </dd>
              </div>
              <div>
                <dt>Opened</dt>
                <dd>{formatTimestamp(p.opened_at) || "—"}</dd>
              </div>
            </dl>
            {stale ? (
              <p className="attention-box" role="status">
                Current market price is outdated. Profit/loss cannot be
                calculated safely. Refresh recent prices, then return here.
              </p>
            ) : stopBreached ? (
              <p className="attention-box" role="alert">
                Stop-loss is breached (price {money(p.mark_price)} vs stop{" "}
                {money(p.stop_loss)}). Argus should close this paper trade on
                the next exit pass.
              </p>
            ) : targetHit ? (
              <p className="attention-box" role="status">
                Profit target reached. Argus should close this paper trade on
                the next exit pass.
              </p>
            ) : (
              <p>
                <strong>What Argus is doing now:</strong> Monitoring this open
                paper position against its stop and target.
              </p>
            )}
            <p className="muted-note">
              {stopBreached
                ? "Exit rule: stop-loss — overdue until the worker closes it."
                : targetHit
                  ? "Exit rule: take-profit — waiting for the worker close."
                  : `Why Argus is continuing to hold: the exit rules have not been met yet${
                      p.state ? ` (state: ${p.state})` : ""
                    }.`}
            </p>
            {portfolioId ? (
              <ClearPaperSymbolButton
                portfolioId={portfolioId}
                symbol={p.symbol}
              />
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
