"use client";

import Link from "next/link";
import { useState } from "react";

import { EmptyState } from "@/components/ui";
import { money } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";

export type ScanCandidate = {
  id: string;
  symbol: string;
  timeframe: string;
  strategy_key: string;
  bias: string;
  stage: string;
  score: string;
  risk_status: string;
  reason_code: string | null;
  reason_text: string | null;
  current_price: string | null;
  entry_zone: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  market_data_at: string | null;
  evaluated_at: string;
};

export function OpportunityRadar({
  candidates,
  scannedCount,
  onSelect,
  selectedId,
}: {
  candidates: ScanCandidate[];
  scannedCount: number;
  onSelect: (id: string) => void;
  selectedId: string | null;
}) {
  const top = candidates
    .filter((c) => c.stage !== "Rejected")
    .concat(candidates.filter((c) => c.stage === "Rejected"))
    .slice(0, 5);

  if (top.length === 0) {
    return (
      <div>
        <EmptyState>
          {scannedCount > 0
            ? `Argus scanned ${scannedCount} markets. No setups currently meet entry requirements.`
            : "No scan results yet. Waiting for the next market scan cycle."}
        </EmptyState>
        <div className="form-actions" style={{ marginTop: "0.75rem" }}>
          <Link className="btn secondary" href="/market">
            Trading Intelligence / Market
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Price</th>
              <th>Bias</th>
              <th>Score</th>
              <th>Strategy</th>
              <th>TF</th>
              <th>Stage</th>
              <th>Risk</th>
              <th>Evaluated</th>
            </tr>
          </thead>
          <tbody>
            {top.map((c) => (
              <tr
                key={c.id}
                className={selectedId === c.id ? "row-selected" : undefined}
                onClick={() => onSelect(c.id)}
                style={{ cursor: "pointer" }}
              >
                <td>{c.symbol}</td>
                <td>
                  {c.current_price == null ? "Unavailable" : money(c.current_price)}
                </td>
                <td>{c.bias}</td>
                <td>{Number(c.score).toFixed(1)}</td>
                <td>{c.strategy_key}</td>
                <td>{c.timeframe}</td>
                <td>{c.stage}</td>
                <td>{c.risk_status}</td>
                <td>{formatTimestamp(c.evaluated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="form-actions" style={{ marginTop: "0.75rem" }}>
        <Link className="btn secondary" href="/market">
          Full Trading Intelligence
        </Link>
      </div>
    </div>
  );
}

export function useSelectedCandidate(candidates: ScanCandidate[]) {
  const [selectedId, setSelectedId] = useState<string | null>(
    candidates.find((c) => c.stage !== "Rejected")?.id ?? candidates[0]?.id ?? null,
  );
  const selected = candidates.find((c) => c.id === selectedId) ?? null;
  return { selectedId, setSelectedId, selected };
}
