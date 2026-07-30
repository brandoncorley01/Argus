"use client";

import { useState } from "react";

type Opportunity = {
  symbol: string;
  stage?: string;
  confidence?: number;
  confidence_label?: string;
  recommendation?: string;
};

type Briefing = {
  institution_status?: string;
  founder_action_required?: string;
  trading_mission?: {
    trading_objective?: string;
    market_outlook?: string;
    risk_environment?: string;
    certification_progress?: {
      days?: number;
      required?: number;
      eligible_for_review?: boolean;
    };
  };
  trading_intelligence_summary?: string[];
  bullets?: string[];
  highest_priority_opportunity?: Opportunity | null;
  certification_progress?: {
    trading_days_counted?: number;
    required_trading_days?: number;
    eligible_for_live_certification_review?: boolean;
  };
  watchlist_intelligence?: {
    markets_watching?: number;
    markets_ready?: number;
    current_recommendation?: string;
    top_opportunities?: Opportunity[];
    waiting_conditions?: string[];
  };
  thinking?: Array<{ text: string; kind?: string }>;
  mode?: string;
};

export function ExecutiveBriefing({
  briefing,
  todayPnl,
  openPositions,
  institutionStatus,
}: {
  briefing: Briefing | null;
  todayPnl: number | null;
  openPositions: number;
  institutionStatus: string;
}) {
  const [open, setOpen] = useState(true);
  const [intelOpen, setIntelOpen] = useState(false);
  const mission = briefing?.trading_mission;
  const cert = briefing?.certification_progress;
  const days = cert?.trading_days_counted ?? mission?.certification_progress?.days ?? 0;
  const need =
    cert?.required_trading_days ?? mission?.certification_progress?.required ?? 30;
  const summary =
    briefing?.trading_intelligence_summary ?? briefing?.bullets ?? [];
  const top = briefing?.highest_priority_opportunity;
  const watch = briefing?.watchlist_intelligence;
  const opportunities = (() => {
    const raw = watch?.top_opportunities ?? [];
    const seen = new Set<string>();
    const out: Opportunity[] = [];
    for (const o of raw) {
      const key = `${o.symbol}|${o.stage ?? ""}|${o.recommendation ?? ""}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(o);
      if (out.length >= 5) break;
    }
    return out;
  })();

  return (
    <section className="panel rise executive-briefing" aria-label="Executive Briefing">
      <button
        type="button"
        className="executive-briefing-toggle"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <h2 style={{ margin: 0 }}>Executive Briefing</h2>
        <span className="muted-note">{open ? "Collapse" : "Expand"}</span>
      </button>
      <p className="muted-note" style={{ marginTop: "0.35rem" }}>
        {briefing?.institution_status ?? institutionStatus} · PROVE mode · Live locked
      </p>

      {open ? (
        <>
          <div className="grid grid-4" style={{ margin: "1rem 0" }}>
            <div>
              <div className="metric-label">Institution status</div>
              <div className="metric-value" style={{ fontSize: "1.15rem" }}>
                {institutionStatus}
              </div>
            </div>
            <div>
              <div className="metric-label">Today&apos;s P&amp;L</div>
              <div className="metric-value" style={{ fontSize: "1.15rem" }}>
                {todayPnl == null ? "Unavailable" : todayPnl.toFixed(2)}
              </div>
            </div>
            <div>
              <div className="metric-label">Open positions</div>
              <div className="metric-value" style={{ fontSize: "1.15rem" }}>
                {openPositions}
              </div>
            </div>
            <div>
              <div className="metric-label">Paper observation</div>
              <div className="metric-value" style={{ fontSize: "1.15rem" }}>
                {days}/{need} days
              </div>
              <p className="muted-note" style={{ margin: "0.25rem 0 0" }}>
                Paper continues until profitable &amp; stable. Live locked.
              </p>
            </div>
          </div>

          <div className="briefing-block">
            <h3>Trading mission</h3>
            <p>{mission?.trading_objective ?? "Protect capital first; paper only."}</p>
            <p className="muted-note">{mission?.market_outlook}</p>
            <p className="muted-note">Risk: {mission?.risk_environment ?? "Unavailable"}</p>
          </div>

          <div className="briefing-block">
            <h3>Trading intelligence</h3>
            <ul className="ops-confidence-list">
              {summary.length > 0 ? (
                summary.slice(0, 5).map((b, i) => (
                  <li key={`sum-${i}-${b.slice(0, 32)}`}>{b}</li>
                ))
              ) : (
                <li className="muted-note">No closed-paper intelligence yet.</li>
              )}
            </ul>
            {(briefing?.thinking ?? []).slice(0, 3).map((t, i) => (
              <p
                key={`think-${i}-${(t.text ?? "").slice(0, 32)}`}
                className="muted-note"
              >
                {t.text}
              </p>
            ))}
          </div>

          <div className="briefing-block">
            <h3>Highest priority opportunity</h3>
            {top ? (
              <p>
                <strong>{top.symbol}</strong> · {top.confidence_label ?? "—"} (
                {top.confidence?.toFixed?.(0) ?? top.confidence}) · {top.stage} ·{" "}
                {top.recommendation}
              </p>
            ) : (
              <p className="muted-note">No opportunity currently meets Ready standards.</p>
            )}
          </div>

          <div className="briefing-block">
            <h3>Founder action required</h3>
            <p>{briefing?.founder_action_required ?? "None — continue observing."}</p>
          </div>

          <details
            className="tech-details"
            open={intelOpen}
            onToggle={(e) => setIntelOpen((e.target as HTMLDetailsElement).open)}
          >
            <summary>Live Market Intelligence</summary>
            <p className="muted-note">
              Watching {watch?.markets_watching ?? 0} · Ready {watch?.markets_ready ?? 0} ·
              Recommendation {watch?.current_recommendation ?? "WAIT"}
            </p>
            {(watch?.waiting_conditions ?? []).slice(0, 3).map((w, i) => (
              <p key={`wait-${i}-${w.slice(0, 24)}`} className="muted-note">
                Waiting: {w}
              </p>
            ))}
            {opportunities.length === 0 ? (
              <p className="muted-note">No top watchlist opportunities.</p>
            ) : (
              <ul className="ops-confidence-list">
                {opportunities.map((o, i) => (
                  <li
                    key={`${o.symbol}-${o.stage ?? "x"}-${o.recommendation ?? "r"}-${i}`}
                  >
                    {o.symbol} · {o.stage} · {o.confidence_label} · {o.recommendation}
                  </li>
                ))}
              </ul>
            )}
          </details>
        </>
      ) : null}
    </section>
  );
}
