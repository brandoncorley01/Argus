"use client";

import Link from "next/link";

import { money } from "@/lib/founder/simple";

import { usePaperLive } from "@/components/founder/PaperLiveProvider";

/**
 * First-glance paper capital — driven by the shared Home pulse.
 * Account = cash + open marks; In trades = cost basis committed; Cash = cash_balance.
 */
export function CapitalStrip() {
  const { account, fetchedAt, refreshing, positions, openUnrealizedPnl } =
    usePaperLive();

  const equity = account.balance != null ? Number(account.balance) : null;
  const inTrades = account.inTrades != null ? Number(account.inTrades) : null;
  const cash = account.cash != null ? Number(account.cash) : null;
  const starting = account.startingCash != null ? Number(account.startingCash) : 300;
  const netVs = account.netVsStart != null ? Number(account.netVsStart) : null;
  const partsOk =
    equity != null &&
    cash != null &&
    inTrades != null &&
    Number.isFinite(equity) &&
    Number.isFinite(cash) &&
    Number.isFinite(inTrades);
  // Equity should track cash + mark value; cost basis can differ from marks.
  const markSum = positions.reduce((sum, p) => {
    const mv = p.market_value != null ? Number(p.market_value) : NaN;
    return sum + (Number.isFinite(mv) ? mv : 0);
  }, 0);
  const implied = cash != null && Number.isFinite(markSum) ? cash + markSum : null;
  const drift =
    partsOk && implied != null && Number.isFinite(implied)
      ? Math.abs(equity! - implied)
      : 0;
  const explanation =
    account.capitalExplanation?.trim() ||
    (cash != null && Number.isFinite(cash) && cash < starting * 0.25
      ? `Started near $${starting.toFixed(0)}. Cash is now ${money(cash)} after paper buys/sells` +
        (account.fillCount ? ` (${account.fillCount} fills)` : "") +
        (netVs != null && Number.isFinite(netVs)
          ? ` — net ${money(netVs)} vs start`
          : "") +
        ". Nothing was withdrawn. Reseed learning desk restores $300 practice cash."
      : null);

  return (
    <section className="panel rise capital-strip" aria-label="Paper capital">
      <div className="capital-strip-head">
        <h2 className="capital-strip-title">Paper capital</h2>
        <p className="muted-note capital-strip-meta">
          {account.openCount} open
          {openUnrealizedPnl != null && Number.isFinite(openUnrealizedPnl)
            ? ` · open P&L ${money(openUnrealizedPnl)}`
            : ""}
          {Number.isFinite(starting) ? ` · started ${money(starting)}` : ""}
          {fetchedAt
            ? refreshing
              ? " · refreshing…"
              : " · live"
            : " · waiting for first pulse"}
        </p>
      </div>
      <div className="capital-strip-grid">
        <div className="capital-metric capital-metric-primary">
          <span className="capital-label">Money in account</span>
          <strong className="capital-value">{money(account.balance)}</strong>
          <span className="capital-hint">
            Total equity (cash + open marks)
          </span>
        </div>
        <div className="capital-metric capital-metric-primary">
          <span className="capital-label">Money in trades</span>
          <strong className="capital-value">{money(account.inTrades)}</strong>
          <span className="capital-hint">Cost basis in open positions</span>
        </div>
        <div className="capital-metric capital-metric-secondary">
          <span className="capital-label">Cash available</span>
          <strong className="capital-value capital-value-sm">
            {money(account.cash)}
          </strong>
          <span className="capital-hint">Remaining paper cash (not in positions)</span>
        </div>
      </div>
      {explanation ? (
        <p className="attention-box capital-strip-story" style={{ marginTop: "0.75rem" }}>
          {explanation}{" "}
          <Link href="/paper-training">Open Paper Training</Link> to reseed if you want a
          fresh $300 practice book.
        </p>
      ) : (
        <p className="muted-note capital-strip-footnote">
          Learning desk targets ~$300 starting cash. Equity moves when prices mark
          open trades or when Argus opens/closes paper positions
          {drift > 1
            ? ` · check: cash + marks ≈ ${money(implied)} vs equity ${money(equity)}`
            : ""}
          .
        </p>
      )}
    </section>
  );
}
