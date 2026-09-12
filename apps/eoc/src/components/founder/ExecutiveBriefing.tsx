"use client";

import { useEffect, useState } from "react";

import { usePaperLiveOptional } from "@/components/founder/PaperLiveProvider";
import { moneyPnl, pnlClass } from "@/lib/founder/simple";
import { todayPnlWindowLabel } from "@/lib/founder/todayPnl";

const BRIEFING_POLL_MS = 15_000;

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
  error?: string;
};

function statusMeaning(status: string): string {
  switch (status) {
    case "Running":
      return "Paper desk is operating normally.";
    case "Paused":
      return "New paper entries are paused; open trades can still be monitored.";
    case "Stopped":
      return "Argus control plane is not ready — Start Argus to resume.";
    case "Warning":
      return "Something needs attention before trusting new paper entries.";
    default:
      return "Status detail unavailable.";
  }
}

export function ExecutiveBriefing({
  briefing: initialBriefing = null,
  todayPnl,
  totalPnl,
  openPositions,
  institutionStatus,
  institutionExplanation,
  institutionFix,
}: {
  briefing?: Briefing | null;
  todayPnl: number | null;
  /** Total account equity minus starting cash; includes current open marks. */
  totalPnl: number | null;
  openPositions: number;
  institutionStatus: string;
  /** Plain-language why for Running / Warning / Paused / Stopped. */
  institutionExplanation?: string | null;
  /** Concrete next step when status is not healthy. */
  institutionFix?: string | null;
}) {
  const [open, setOpen] = useState(true);
  const [intelOpen, setIntelOpen] = useState(false);
  const [briefing, setBriefing] = useState<Briefing | null>(initialBriefing);
  const [loaded, setLoaded] = useState(Boolean(initialBriefing));
  const [loadError, setLoadError] = useState<string | null>(
    initialBriefing?.error ? String(initialBriefing.error) : null,
  );

  useEffect(() => {
    if (initialBriefing) {
      setBriefing(initialBriefing);
      setLoaded(true);
    }
  }, [initialBriefing]);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;
    const load = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await fetch("/api/founder/briefing", {
          cache: "no-store",
          signal: AbortSignal.timeout(25_000),
        });
        const data = (await res.json()) as Briefing;
        if (cancelled) return;
        setBriefing(data);
        setLoadError(data.error ? String(data.error) : null);
        setLoaded(true);
      } catch {
        if (!cancelled) {
          setLoaded(true);
          setLoadError((prev) => prev ?? "Briefing timed out — retrying…");
        }
      } finally {
        inFlight = false;
      }
    };
    void load();
    const id = window.setInterval(load, BRIEFING_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const mission = briefing?.trading_mission;
  const cert = briefing?.certification_progress;
  const days = cert?.trading_days_counted ?? mission?.certification_progress?.days ?? 0;
  const need =
    cert?.required_trading_days ?? mission?.certification_progress?.required ?? 30;
  const summary =
    briefing?.trading_intelligence_summary ?? briefing?.bullets ?? [];
  const watch = briefing?.watchlist_intelligence;
  const top =
    briefing?.highest_priority_opportunity ??
    watch?.top_opportunities?.[0] ??
    null;
  const statusWhy =
    (institutionExplanation && institutionExplanation.trim()) ||
    statusMeaning(institutionStatus);
  const statusFix = institutionFix?.trim() || null;
  const live = usePaperLiveOptional();
  const liveOpen = live?.account.openCount ?? openPositions;
  const liveTodayPnl =
    live?.todayEquityPnl != null ? live.todayEquityPnl : todayPnl;
  const liveTodayBasis = live?.todayPnlBasis ?? null;
  const liveTodayRealized =
    live?.totalRealizedPnl != null ? live.totalRealizedPnl : null;
  const liveTotalPnl =
    live?.account.totalPnl != null &&
    Number.isFinite(Number(live.account.totalPnl))
      ? Number(live.account.totalPnl)
      : totalPnl;
  const greenTodayButDownOverall =
    liveTodayPnl != null &&
    liveTodayPnl > 0 &&
    liveTotalPnl != null &&
    liveTotalPnl <= 0;
  const todayUsesAgedMarks =
    liveTodayBasis === "account_equity_change_since_midnight_open_marks_aged";
  const displayTodayPnl =
    liveTodayPnl != null
      ? liveTodayPnl
      : liveTodayRealized != null
        ? liveTodayRealized
        : null;
  const todayLabel =
    liveTodayPnl != null
      ? "Today's account P&L"
      : liveTodayRealized != null
        ? "Today's realized P&L"
        : "Today's account P&L";
  const todayHint =
    liveTodayPnl != null
      ? todayUsesAgedMarks
        ? `${todayPnlWindowLabel()} · open marks aged through a price-feed gap`
        : `${todayPnlWindowLabel()} · realized trades + open position marks`
      : liveTodayRealized != null
        ? `${todayPnlWindowLabel()} · account change unavailable; closed trades only`
        : `${todayPnlWindowLabel()} · realized trades + open position marks`;
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
        {loaded ? "" : " · loading…"}
        {loadError ? " · partial" : ""}
      </p>
      <p className="institution-status-why" style={{ marginTop: "0.35rem" }}>
        {statusWhy}
      </p>
      {statusFix ? (
        <p className="institution-status-fix">{statusFix}</p>
      ) : null}

      {open ? (
        <>
          <div className="grid grid-4" style={{ margin: "1rem 0" }}>
            <div>
              <div className="metric-label">Institution status</div>
              <div className="metric-value" style={{ fontSize: "1.15rem" }}>
                {institutionStatus}
              </div>
              <p
                className="muted-note institution-status-detail"
                style={{ margin: "0.35rem 0 0" }}
              >
                {statusWhy}
              </p>
              {statusFix ? (
                <p
                  className="institution-status-fix"
                  style={{ marginTop: "0.45rem" }}
                >
                  {statusFix}
                </p>
              ) : null}
            </div>
            <div>
              <div className="metric-label">{todayLabel}</div>
              <div
                className={`metric-value ${pnlClass(displayTodayPnl)}`}
                style={{ fontSize: "1.15rem" }}
              >
                {displayTodayPnl == null ? "Unavailable" : moneyPnl(displayTodayPnl)}
              </div>
              <p className="muted-note" style={{ margin: "0.25rem 0 0" }}>
                {todayHint}
              </p>
              <div className="metric-label" style={{ marginTop: "0.65rem" }}>
                Total P&amp;L
              </div>
              <div
                className={`metric-value ${pnlClass(liveTotalPnl)}`}
                style={{ fontSize: "1.15rem" }}
              >
                {liveTotalPnl == null ? "Unavailable" : moneyPnl(liveTotalPnl)}
              </div>
              <p className="muted-note" style={{ margin: "0.25rem 0 0" }}>
                Since desk start · includes open position marks
              </p>
              {greenTodayButDownOverall ? (
                <p className="institution-status-fix" style={{ marginTop: "0.4rem" }}>
                  Green today, but still losing overall. Total P&amp;L controls the
                  profitability verdict.
                </p>
              ) : null}
            </div>
            <div>
              <div className="metric-label">Open positions</div>
              <div className="metric-value" style={{ fontSize: "1.15rem" }}>
                {liveOpen}
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
            <p>
              {mission?.trading_objective ??
                "Protect capital first; take only high-confidence paper setups."}
            </p>
            <p className="muted-note">
              {mission?.market_outlook ??
                (loaded ? "Market outlook unavailable" : "Loading market outlook…")}
            </p>
            <p className="muted-note">
              Risk: {mission?.risk_environment ?? (loaded ? "Unavailable" : "Loading…")}
            </p>
          </div>

          <div className="briefing-block">
            <h3>Trading intelligence</h3>
            <ul className="ops-confidence-list">
              {summary.length > 0 ? (
                summary.slice(0, 6).map((b, i) => (
                  <li key={`sum-${i}-${b.slice(0, 32)}`}>{b}</li>
                ))
              ) : (
                <li className="muted-note">
                  {loaded
                    ? "No intelligence bullets yet — scans will fill this."
                    : "Loading paper intelligence…"}
                </li>
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
                {typeof top.confidence === "number"
                  ? top.confidence.toFixed(0)
                  : (top.confidence ?? "—")}
                ) · {top.stage} · {top.recommendation}
              </p>
            ) : (
              <p className="muted-note">
                {!loaded
                  ? "Loading opportunities…"
                  : (watch?.markets_watching ?? 0) > 0
                    ? `Watching ${watch?.markets_watching} markets — none Ready yet (${watch?.current_recommendation ?? "WAIT"}).`
                    : "No opportunity currently meets Ready standards."}
              </p>
            )}
          </div>

          <div className="briefing-block">
            <h3>Founder action required</h3>
            <p>
              {briefing?.founder_action_required ??
                (loaded ? "None — continue observing." : "Loading…")}
            </p>
          </div>

          <details
            className="tech-details"
            open={intelOpen}
            onToggle={(e) => setIntelOpen((e.target as HTMLDetailsElement).open)}
          >
            <summary>Live Market Intelligence</summary>
            <p className="muted-note">
              Watching {watch?.markets_watching ?? 0} · Ready{" "}
              {watch?.markets_ready ?? 0} · Recommendation{" "}
              {watch?.current_recommendation ?? "WAIT"}
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
