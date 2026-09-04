"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import { EmptyState } from "@/components/ui";
import { teachScanAction } from "@/lib/actions/paper";
import { REJECTION_LABELS } from "@/lib/founder/decisionStream";
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

function whyText(c: ScanCandidate): string {
  if (c.reason_text) return c.reason_text;
  if (c.reason_code && REJECTION_LABELS[c.reason_code]) {
    return REJECTION_LABELS[c.reason_code];
  }
  if (c.stage === "Watching") return "Setup looks interesting — waiting for confirmation.";
  return "No extra reason stored.";
}

function strategyLabel(strategyKey: string | null | undefined): string {
  const key = (strategyKey || "").toLowerCase();
  const labels: Record<string, string> = {
    sma_crossover: "Momentum (SMA)",
    grid_trading: "Grid (range)",
    dca: "DCA (dip average)",
    trend_momentum: "Trend / momentum (RSI+MACD)",
    cross_venue_arb: "Cross-venue spread",
    momentum_continuation: "Momentum continuation",
    breakout: "Breakout",
    dip_pullback_reversal: "Dip / pullback",
    range_mean_reversion: "Range mean reversion",
    peak_exhaustion_protection: "Peak protection",
  };
  return labels[key] || strategyKey || "unknown";
}

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
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [note, setNote] = useState<string | null>(null);

  const top = candidates
    .filter((c) => c.stage !== "Rejected")
    .concat(candidates.filter((c) => c.stage === "Rejected"))
    .slice(0, 5);

  function teach(
    c: ScanCandidate,
    signal: "interested" | "not_interested" | "needs_more_data" | "looks_wrong",
  ) {
    setNote(null);
    startTransition(async () => {
      const res = await teachScanAction({
        symbol: c.symbol,
        signal,
        candidateId: c.id,
      });
      setNote(res.message);
      router.refresh();
    });
  }

  if (top.length === 0) {
    return (
      <div>
        <EmptyState>
          {scannedCount > 0
            ? `Argus checked ${scannedCount} markets. Nothing met the entry rules this cycle — that can be healthy.`
            : "No scan results yet. Press “Scan markets now” above."}
        </EmptyState>
        <div className="form-actions" style={{ marginTop: "0.75rem" }}>
          <Link className="btn secondary" href="/market">
            Open Market data
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="opportunity-radar">
      <ul className="opportunity-cards">
        {top.map((c) => {
          const selected = selectedId === c.id;
          return (
            <li key={c.id}>
              <button
                type="button"
                className={`opportunity-card ${selected ? "row-selected" : ""}`}
                onClick={() => onSelect(c.id)}
              >
                <div className="opportunity-card-head">
                  <strong>{c.symbol}</strong>
                  <span className={`stage-pill stage-${c.stage.toLowerCase().replace(/\s+/g, "-")}`}>
                    {c.stage}
                  </span>
                </div>
                <div className="opportunity-card-meta">
                  <span>
                    Price{" "}
                    {c.current_price == null ? "Unavailable" : money(c.current_price)}
                  </span>
                  <span>{c.bias}</span>
                  <span>Score {Number(c.score).toFixed(0)}</span>
                    <span>
                    {strategyLabel(c.strategy_key)} · {c.timeframe}
                  </span>
                </div>
                <p className="opportunity-why">
                  <strong>Why: </strong>
                  {whyText(c)}
                </p>
                <p className="muted-note" style={{ margin: "0.25rem 0 0" }}>
                  Checked {formatTimestamp(c.evaluated_at)}
                </p>
              </button>
              <div className="teach-actions">
                <button
                  type="button"
                  className="btn secondary"
                  disabled={pending}
                  onClick={() => teach(c, "interested")}
                >
                  Looks good
                </button>
                <button
                  type="button"
                  className="btn secondary"
                  disabled={pending}
                  onClick={() => teach(c, "not_interested")}
                >
                  Skip this
                </button>
                <button
                  type="button"
                  className="btn secondary"
                  disabled={pending}
                  onClick={() => teach(c, "needs_more_data")}
                >
                  Need more data
                </button>
                <button
                  type="button"
                  className="btn secondary"
                  disabled={pending}
                  onClick={() => teach(c, "looks_wrong")}
                >
                  Looks wrong
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      {note ? (
        <p className="control-feedback ok" role="status">
          {note}
        </p>
      ) : (
        <p className="muted-note">
          Teaching buttons save your preference for paper practice. They do not place
          trades or spend real money.
        </p>
      )}
      <div className="form-actions" style={{ marginTop: "0.5rem" }}>
        <Link className="btn secondary" href="/market">
          Open Market data
        </Link>
      </div>
    </div>
  );
}
