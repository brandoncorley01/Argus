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

/** Minimal verified close series — not a decorative indicator set. */
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
        Select a candidate from Opportunity Radar to inspect verified price data.
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
          Price{" "}
          {candidate.current_price == null
            ? "Unavailable"
            : money(candidate.current_price)}
        </span>
        <span>Stage {candidate.stage}</span>
        <span>Updated {formatTimestamp(candidate.market_data_at)}</span>
      </div>

      {!hasChart ? (
        <EmptyState>
          Chart-quality candle series unavailable for {candidate.symbol}. Persisted
          OHLCV bars are required — nothing is invented. Open Market for bar tables
          when ingest has data.
        </EmptyState>
      ) : (
        <PriceSparkline values={closes} />
      )}

      <ul className="plain-list">
        <li>
          Entry zone:{" "}
          {candidate.entry_zone == null ? "Unavailable" : money(candidate.entry_zone)}
        </li>
        <li>
          Stop-loss:{" "}
          {candidate.stop_loss == null ? "Unavailable" : money(candidate.stop_loss)}
        </li>
        <li>
          Profit target:{" "}
          {candidate.take_profit == null
            ? "Unavailable"
            : money(candidate.take_profit)}
        </li>
        <li>
          Indicators used by active probe: SMA fast/slow ({candidate.strategy_key}).
          No decorative indicators are added.
        </li>
        <li>{candidate.reason_text ?? "No additional reason text."}</li>
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
      <polyline
        fill="none"
        stroke="var(--accent)"
        strokeWidth="2"
        points={pts}
      />
    </svg>
  );
}
