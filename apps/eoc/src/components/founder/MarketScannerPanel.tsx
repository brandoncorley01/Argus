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
        Scanner status unavailable. Start Argus and wait for the worker scan cron,
        or ensure market scan APIs are reachable. No activity is fabricated.
      </EmptyState>
    );
  }

  const cycle = status.cycle;
  const progress =
    cycle && cycle.symbols_total > 0
      ? Math.round((cycle.symbols_scanned / cycle.symbols_total) * 100)
      : null;

  return (
    <div className="scanner-panel">
      <div className="summary-grid summary-grid-compact">
        <div className="summary-card">
          <span className="metric-label">Scanner state</span>
          <strong>{status.scanner_state}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Current cycle</span>
          <strong>
            {cycle ? `${cycle.symbols_scanned}/${cycle.symbols_total}` : "None yet"}
          </strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Evaluating</span>
          <strong>{cycle?.current_symbol ?? "—"}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Symbols monitored</span>
          <strong>{status.symbols_monitored}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Scan progress</span>
          <strong>{progress == null ? "—" : `${progress}%`}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Last scan completion</span>
          <strong>{formatTimestamp(cycle?.completed_at) || "Unavailable"}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Next scheduled scan</span>
          <strong>
            {formatTimestamp(status.next_scheduled_at ?? cycle?.next_scheduled_at) ||
              "Unavailable"}
          </strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Market-data age</span>
          <strong>
            {status.market_data_age_seconds == null
              ? "Unavailable"
              : `${Math.round(status.market_data_age_seconds / 60)} min`}
            {status.market_data_stale ? " (stale)" : ""}
          </strong>
        </div>
      </div>

      <h3 className="section-subhead">Live scanner feed</h3>
      {feed.length === 0 ? (
        <EmptyState>
          No scan events yet. The worker runs an observation-only scan about every
          two minutes once instruments and bars exist.
        </EmptyState>
      ) : (
        <ul className="activity-feed scanner-feed">
          {feed.slice(0, 8).map((item) => (
            <li key={item.id} className={`activity-item activity-${item.tone}`}>
              <div className="activity-when">{formatTimestamp(item.at)}</div>
              <div className="activity-title">
                {item.symbol ? `${item.symbol} · ` : ""}
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
