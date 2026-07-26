"use client";

import { EmptyState } from "@/components/ui";
import { formatTimestamp } from "@/lib/format";
import type { DecisionItem } from "@/lib/founder/decisionStream";

export type ScanStatus = {
  scanner_state: string;
  cycle: {
    id: string;
    status: string;
    timeframe: string;
    strategy_key: string;
    symbols_total: number;
    symbols_scanned: number;
    candidates_found: number;
    current_symbol: string | null;
    started_at: string;
    completed_at: string | null;
    next_scheduled_at: string | null;
  } | null;
  symbols_monitored: number;
  market_data_at: string | null;
  market_data_age_seconds: number | null;
  market_data_stale: boolean;
  next_scheduled_at: string | null;
  worker_note?: string;
};

const STATE_PLAIN: Record<string, string> = {
  Scanning: "Looking at markets right now",
  "Between Cycles": "Resting until the next scan",
  Paused: "Trading paused — scans may still run",
  Delayed: "Scan is late — worker catching up",
  Failed: "Scanner cannot run yet",
};

export function MarketScannerPanel({
  status,
  feed,
}: {
  status: ScanStatus | null;
  feed: DecisionItem[];
}) {
  if (!status) {
    return (
      <EmptyState>
        Could not load scanner status. If Opportunity Radar still shows symbols, a scan
        already ran — press “Scan markets now” to refresh.
      </EmptyState>
    );
  }

  const cycle = status.cycle;
  const progress =
    cycle && cycle.symbols_total > 0
      ? Math.round((cycle.symbols_scanned / cycle.symbols_total) * 100)
      : null;
  const plain = STATE_PLAIN[status.scanner_state] ?? status.scanner_state;

  return (
    <div className="scanner-panel">
      <p className="scanner-plain">{plain}</p>
      <div className="summary-grid summary-grid-compact">
        <div className="summary-card">
          <span className="metric-label">Checking now</span>
          <strong>{cycle?.current_symbol ?? "Nothing right now"}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Markets in last scan</span>
          <strong>
            {cycle
              ? `${cycle.symbols_scanned} of ${cycle.symbols_total}`
              : "None yet"}
          </strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Progress</span>
          <strong>{progress == null ? "—" : `${progress}%`}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Markets on watchlist</span>
          <strong>{status.symbols_monitored}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Last finished</span>
          <strong>{formatTimestamp(cycle?.completed_at) || "Not yet"}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Next scan</span>
          <strong>
            {formatTimestamp(status.next_scheduled_at ?? cycle?.next_scheduled_at) ||
              "When you press Scan or the worker runs"}
          </strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Price data age</span>
          <strong>
            {status.market_data_age_seconds == null
              ? "No bars loaded yet"
              : `${Math.round(status.market_data_age_seconds / 60)} min old`}
            {status.market_data_stale ? " — too old for entries" : ""}
          </strong>
        </div>
      </div>

      <h3 className="section-subhead">Latest scan steps</h3>
      {feed.length === 0 ? (
        <EmptyState>
          No scan steps yet. Press “Scan markets now”.
        </EmptyState>
      ) : (
        <ul className="activity-feed scanner-feed">
          {feed.slice(0, 6).map((item) => (
            <li key={item.id} className={`activity-item activity-${item.tone}`}>
              <div className="activity-when">{formatTimestamp(item.at)}</div>
              <div className="activity-title">
                {item.symbol ? `${item.symbol}: ` : ""}
                {item.event}
              </div>
              <div className="activity-detail">{item.reason}</div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
