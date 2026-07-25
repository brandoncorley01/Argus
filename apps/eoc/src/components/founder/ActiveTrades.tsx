"use client";

import { useState } from "react";

import { EmptyState } from "@/components/ui";
import { money, pnlClass } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";

export type PositionSummary = {
  id: string;
  symbol: string;
  quantity: string;
  side: string;
  average_cost: string;
  committed_capital: string;
  realized_pnl: string;
  unrealized_pnl: string;
  mark_price: string | null;
  pnl_percent: string | null;
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
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Side</th>
              <th>
                Entry <Tip text="Average fill cost for this paper position." />
              </th>
              <th>
                Current{" "}
                <Tip text="Mark price when the paper book has a real mark; otherwise Unavailable." />
              </th>
              <th>Qty</th>
              <th>
                Committed{" "}
                <Tip text="Absolute quantity × average cost (paper capital in the trade)." />
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
            {positions.map((p) => (
              <tr
                key={p.id}
                className={selected === p.id ? "row-selected" : undefined}
                onClick={() => setSelected(p.id)}
                style={{ cursor: "pointer" }}
              >
                <td>{p.symbol}</td>
                <td>{p.side === "long" ? "Long" : "Short"}</td>
                <td>{money(p.average_cost)}</td>
                <td>{p.mark_price == null ? "Unavailable" : money(p.mark_price)}</td>
                <td>{p.quantity}</td>
                <td>{money(p.committed_capital)}</td>
                <td className={pnlClass(p.unrealized_pnl)}>{money(p.unrealized_pnl)}</td>
                <td className={pnlClass(p.pnl_percent)}>
                  {p.pnl_percent == null
                    ? "Unavailable"
                    : `${Number(p.pnl_percent).toFixed(2)}%`}
                </td>
                <td>{p.stop_loss == null ? "Unavailable" : money(p.stop_loss)}</td>
                <td>{p.take_profit == null ? "Unavailable" : money(p.take_profit)}</td>
                <td>{formatTimestamp(p.opened_at)}</td>
                <td>{p.state}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {current ? (
        <div className="position-detail panel" style={{ marginTop: "0.75rem" }}>
          <h3 style={{ marginTop: 0 }}>{current.symbol} detail</h3>
          <ul className="plain-list">
            <li>
              Strategy / signal:{" "}
              {current.strategy_version_id
                ? `version ${current.strategy_version_id.slice(0, 8)}…`
                : "Unavailable"}
            </li>
            <li>State: {current.state}</li>
            <li>
              Stop-loss / take-profit are not persisted on paper positions yet —
              shown as Unavailable rather than invented.
            </li>
            <li>
              Manual close controls are not offered here. Use audited Advanced
              paper workflows if an exit must be forced.
            </li>
          </ul>
        </div>
      ) : (
        <p className="muted-note">Select a position to view detail.</p>
      )}
    </div>
  );
}
