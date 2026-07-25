"use client";

import { useState } from "react";

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

function Tip({ text }: { text: string }) {
  return (
    <span className="info-tip" title={text} aria-label={text}>
      ?
    </span>
  );
}

export function ActiveTrades({ positions }: { positions: PositionSummary[] }) {
  const [selected, setSelected] = useState<string | null>(null);
  const current = positions.find((p) => p.id === selected) ?? null;

  if (positions.length === 0) {
    return (
      <EmptyState>
        No open paper positions. When Argus enters a trade, it will show here with
        entry, commitment, and P&amp;L.
      </EmptyState>
    );
  }

  return (
    <div className="active-trades">
      <div className="table-wrap active-trades-desktop">
        <table className="data">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>
                Entry price{" "}
                <Tip text="Average fill price per unit — not committed capital." />
              </th>
              <th>
                Current{" "}
                <Tip text="Latest market OHLCV close when available; otherwise Unavailable." />
              </th>
              <th>Qty</th>
              <th>
                Capital{" "}
                <Tip text="|Qty| × entry price (cost basis committed)." />
              </th>
              <th>
                Mkt value{" "}
                <Tip text="|Qty| × current mark when a mark exists." />
              </th>
              <th>P&amp;L $</th>
              <th>P&amp;L %</th>
              <th>Stop</th>
              <th>Target</th>
              <th>Opened</th>
              <th>State</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => {
              const incomplete =
                p.price_status === "unavailable" || p.price_status === "stale";
              return (
                <tr
                  key={p.id}
                  className={selected === p.id ? "row-selected" : undefined}
                  onClick={() => setSelected(p.id)}
                  style={{ cursor: "pointer" }}
                >
                  <td>{p.symbol}</td>
                  <td>{p.side === "long" ? "Long" : "Short"}</td>
                  <td>{money(p.average_cost)}</td>
                  <td>
                    {p.mark_price == null
                      ? "Unavailable"
                      : `${money(p.mark_price)}${p.price_status === "stale" ? " (stale)" : ""}`}
                  </td>
                  <td>{p.quantity}</td>
                  <td>{money(p.committed_capital)}</td>
                  <td>
                    {p.market_value == null ? "Unavailable" : money(p.market_value)}
                  </td>
                  <td className={pnlClass(p.unrealized_pnl)}>
                    {incomplete || p.unrealized_pnl == null
                      ? "Unavailable"
                      : moneyPnl(p.unrealized_pnl)}
                  </td>
                  <td className={pnlClass(p.pnl_percent)}>
                    {p.pnl_percent == null
                      ? "Unavailable"
                      : `${Number(p.pnl_percent).toFixed(2)}%`}
                  </td>
                  <td>{p.stop_loss == null ? "Unavailable" : money(p.stop_loss)}</td>
                  <td>
                    {p.take_profit == null ? "Unavailable" : money(p.take_profit)}
                  </td>
                  <td>{formatTimestamp(p.opened_at)}</td>
                  <td>{p.state}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <div className="active-trades-mobile">
        {positions.map((p) => {
          const incomplete =
            p.price_status === "unavailable" || p.price_status === "stale";
          return (
            <button
              key={p.id}
              type="button"
              className={`position-card ${selected === p.id ? "row-selected" : ""}`}
              onClick={() => setSelected(p.id)}
            >
              <div className="position-card-head">
                <strong>{p.symbol}</strong>
                <span>{p.side === "long" ? "Long" : "Short"}</span>
              </div>
              <div className="position-card-grid">
                <span>Entry {money(p.average_cost)}</span>
                <span>
                  Current{" "}
                  {p.mark_price == null ? "Unavailable" : money(p.mark_price)}
                </span>
                <span>Capital {money(p.committed_capital)}</span>
                <span className={pnlClass(p.unrealized_pnl)}>
                  P&amp;L{" "}
                  {incomplete || p.unrealized_pnl == null
                    ? "Unavailable"
                    : moneyPnl(p.unrealized_pnl)}
                </span>
              </div>
              <p className="muted-note" style={{ margin: "0.35rem 0 0" }}>
                {p.state}
              </p>
            </button>
          );
        })}
      </div>

      {current ? (
        <div className="position-detail panel" style={{ marginTop: "0.75rem" }}>
          <h3 style={{ marginTop: 0 }}>{current.symbol} detail</h3>
          <ul className="plain-list">
            <li>
              Entry price is the average fill price per unit (
              {money(current.average_cost)}), not capital committed (
              {money(current.committed_capital)}).
            </li>
            <li>
              Price status: {current.price_status ?? "unavailable"}.
              {current.price_status === "unavailable"
                ? " No market OHLCV mark found for this symbol — unrealized P&L is not shown as zero."
                : null}
              {current.price_status === "stale"
                ? " Latest bar is older than freshness policy."
                : null}
            </li>
            <li>
              Strategy / signal:{" "}
              {current.strategy_version_id
                ? `version ${current.strategy_version_id.slice(0, 8)}…`
                : "Unavailable"}
            </li>
            <li>
              Stop-loss / take-profit are not persisted on paper positions yet.
            </li>
          </ul>
        </div>
      ) : (
        <p className="muted-note">Select a position to view detail.</p>
      )}
    </div>
  );
}
