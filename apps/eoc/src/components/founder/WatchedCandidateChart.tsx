"use client";

import { EmptyState } from "@/components/ui";
import { money } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";
import type { ScanCandidate } from "@/components/founder/OpportunityRadar";

export type ScanBar = {
  open_time: string;
  close_time: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string | null;
};

export function WatchedCandidateChart({
  candidate,
  bars,
  timeframe,
}: {
  candidate: ScanCandidate | null;
  bars: ScanBar[];
  timeframe: string | null;
}) {
  if (!candidate) {
    return (
      <EmptyState>
        Tap a market card on the left to see what Argus thought about it.
      </EmptyState>
    );
  }

  const closes = bars.map((b) => Number(b.close)).filter((n) => Number.isFinite(n));
  const hasChart = closes.length >= 2;

  return (
    <div className="watched-chart">
      <div className="watched-meta">
        <strong>
          {candidate.symbol} · {timeframe ?? candidate.timeframe}
        </strong>
        <span>
          Last price{" "}
          {candidate.current_price == null
            ? "Unavailable"
            : money(candidate.current_price)}
        </span>
        <span>{candidate.stage}</span>
        <span>Data {formatTimestamp(candidate.market_data_at)}</span>
      </div>

      {!hasChart ? (
        <EmptyState>
          Not enough stored candles to draw a chart for {candidate.symbol} (
          {closes.length} bar{closes.length === 1 ? "" : "s"}). Argus still used
          whatever bars exist for the decision — ingest more history on Market to
          unlock the chart.
        </EmptyState>
      ) : (
        <>
          <PriceSparkline values={closes} />
          <p className="muted-note">Verified closes only — no decorative indicators.</p>
        </>
      )}

      <ul className="plain-list">
        <li>
          <strong>Plain English: </strong>
          {candidate.reason_text ??
            (candidate.stage === "Rejected"
              ? "Argus skipped this setup."
              : "Argus is watching this setup.")}
        </li>
        <li>
          Suggested entry:{" "}
          {candidate.entry_zone == null ? "Not calculated" : money(candidate.entry_zone)}
        </li>
        <li>
          Stop: {candidate.stop_loss == null ? "Not set" : money(candidate.stop_loss)}
        </li>
        <li>
          Target:{" "}
          {candidate.take_profit == null ? "Not set" : money(candidate.take_profit)}
        </li>
      </ul>
    </div>
  );
}

function PriceSparkline({ values }: { values: number[] }) {
  const w = 560;
  const h = 140;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const pts = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * (w - 8) + 4;
      const y = h - 8 - ((v - min) / span) * (h - 16);
      return `${x},${y}`;
    })
    .join(" ");
  return (
    <svg
      className="price-sparkline"
      viewBox={`0 0 ${w} ${h}`}
      role="img"
      aria-label="Verified close prices"
    >
      <polyline fill="none" stroke="var(--accent)" strokeWidth="2" points={pts} />
    </svg>
  );
}
