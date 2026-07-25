"use client";

import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";

import {
  coachingSkipAction,
  coachingTakeAction,
  recordTrainingFeedbackAction,
  setTrainingModeAction,
} from "@/lib/actions/paper";
import { FEEDBACK_OPTIONS } from "@/lib/founder/plainLanguage";
import { money, moneyPnl, pnlClass } from "@/lib/founder/simple";

type Candidate = {
  id: string;
  symbol: string;
  outlook: string;
  decision: string;
  why: string;
  waiting_for: string;
  confidence: string;
  current_price: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  lesson?: {
    what_argus_sees?: string;
    why_it_may_work?: string;
    what_could_fail?: string;
    planned_entry?: string | null;
    planned_stop?: string | null;
    planned_target?: string | null;
    conditions?: string;
  } | null;
};

type Scorecard = {
  paper_trades_completed: number;
  win_rate: string | null;
  total_paper_pnl: string;
  average_win: string | null;
  average_loss: string | null;
  profit_factor: string | null;
  maximum_drawdown: string | null;
  trades_with_founder_feedback: number;
  live_readiness: string;
  live_readiness_detail: string;
  disclaimer: string;
};

type ClosedTrade = {
  fill_id: string;
  symbol: string;
  realized_pnl: string;
  filled_at: string;
  exit_reason: string | null;
};

export function PaperTrainingClient({
  portfolioId,
  mode,
  defaultNotional,
  candidates,
  scorecard,
  closedTrades,
  readinessNextStep,
}: {
  portfolioId: string;
  mode: "automatic" | "coaching";
  defaultNotional: string;
  candidates: Candidate[];
  scorecard: Scorecard | null;
  closedTrades: ClosedTrade[];
  readinessNextStep: string | null;
}) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const [message, setMessage] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [feedbackCode, setFeedbackCode] = useState<string>(FEEDBACK_OPTIONS[0].code);
  const [feedbackSymbol, setFeedbackSymbol] = useState(
    closedTrades[0]?.symbol ?? candidates[0]?.symbol ?? "BTC-USD",
  );

  const actionable = candidates.filter((c) =>
    ["Watching", "Ready"].includes(c.decision),
  );

  return (
    <div className="paper-training-lab">
      {readinessNextStep ? (
        <p className="attention-box" role="status">
          {readinessNextStep}
        </p>
      ) : null}

      <section className="panel rise" aria-label="Practice modes">
        <h2 style={{ marginTop: 0 }}>Choose how you practice</h2>
        <div className="mode-cards">
          <article className={`mode-card ${mode === "automatic" ? "is-active" : ""}`}>
            <h3>Automatic Practice</h3>
            <p>
              Argus independently scans, opens, manages, and closes simulated
              trades according to approved strategies and risk rules. You observe
              and evaluate — you do not approve every trade.
            </p>
            <button
              type="button"
              className="btn"
              disabled={pending || mode === "automatic"}
              onClick={() => {
                startTransition(async () => {
                  const res = await setTrainingModeAction({
                    portfolioId,
                    mode: "automatic",
                    defaultNotional,
                  });
                  setMessage(res.message);
                  router.refresh();
                });
              }}
            >
              {mode === "automatic" ? "Active" : "Use Automatic Practice"}
            </button>
          </article>
          <article className={`mode-card ${mode === "coaching" ? "is-active" : ""}`}>
            <h3>Coaching Mode</h3>
            <p>
              Argus presents a simulated trade plan before entry. You can Let
              Argus take it, Skip it, ask for the lesson, and leave feedback.
              Coaching Mode never becomes an approval step for Live trading.
            </p>
            <button
              type="button"
              className="btn"
              disabled={pending || mode === "coaching"}
              onClick={() => {
                startTransition(async () => {
                  const res = await setTrainingModeAction({
                    portfolioId,
                    mode: "coaching",
                    defaultNotional,
                  });
                  setMessage(res.message);
                  router.refresh();
                });
              }}
            >
              {mode === "coaching" ? "Active" : "Use Coaching Mode"}
            </button>
          </article>
        </div>
        <p className="muted-note">
          Default paper investment per practice entry: {money(defaultNotional)}{" "}
          (simulated).
        </p>
      </section>

      <section className="panel rise" aria-label="Coaching desk">
        <h2 style={{ marginTop: 0 }}>
          {mode === "coaching" ? "Coaching desk" : "Ideas Argus may enter automatically"}
        </h2>
        {actionable.length === 0 ? (
          <p className="muted-note">
            No actionable ideas right now. Refresh recent prices on Home, then
            scan markets.
          </p>
        ) : (
          <div className="considering-list">
            {actionable.map((c) => (
              <article key={c.id} className="considering-card">
                <header className="considering-card-head">
                  <h3>{c.symbol}</h3>
                  <span className="decision-pill">{c.decision}</span>
                </header>
                <p>
                  <strong>Outlook:</strong> {c.outlook} ·{" "}
                  <strong>Confidence:</strong> {c.confidence}
                </p>
                <p>
                  <strong>Why:</strong> {c.why}
                </p>
                <p>
                  <strong>Waiting for:</strong> {c.waiting_for}
                </p>
                {c.lesson ? (
                  <details className="trade-lesson">
                    <summary>Trade lesson (before entry)</summary>
                    <ul>
                      <li>
                        <strong>What Argus sees:</strong> {c.lesson.what_argus_sees}
                      </li>
                      <li>
                        <strong>Why it may work:</strong> {c.lesson.why_it_may_work}
                      </li>
                      <li>
                        <strong>What could fail:</strong> {c.lesson.what_could_fail}
                      </li>
                      <li>
                        <strong>Planned entry:</strong>{" "}
                        {c.lesson.planned_entry ?? c.current_price ?? "—"}
                      </li>
                      <li>
                        <strong>Planned stop:</strong>{" "}
                        {c.lesson.planned_stop ?? c.stop_loss ?? "—"}
                      </li>
                      <li>
                        <strong>Planned target:</strong>{" "}
                        {c.lesson.planned_target ?? c.take_profit ?? "—"}
                      </li>
                      <li>
                        <strong>Conditions:</strong> {c.lesson.conditions}
                      </li>
                    </ul>
                  </details>
                ) : null}
                {mode === "coaching" ? (
                  <div className="coach-actions">
                    <label>
                      Personal note
                      <input
                        value={note}
                        onChange={(e) => setNote(e.target.value)}
                        placeholder="Optional note"
                      />
                    </label>
                    <button
                      type="button"
                      className="btn control-btn control-btn-start"
                      disabled={pending}
                      onClick={() => {
                        startTransition(async () => {
                          const res = await coachingTakeAction({
                            portfolioId,
                            candidateId: c.id,
                            note: note || undefined,
                          });
                          setMessage(res.message);
                          router.refresh();
                        });
                      }}
                    >
                      Let Argus take this simulated trade
                    </button>
                    <button
                      type="button"
                      className="btn secondary"
                      disabled={pending}
                      onClick={() => {
                        startTransition(async () => {
                          const res = await coachingSkipAction({
                            portfolioId,
                            candidateId: c.id,
                            note: note || undefined,
                          });
                          setMessage(res.message);
                          router.refresh();
                        });
                      }}
                    >
                      Skip
                    </button>
                  </div>
                ) : (
                  <p className="muted-note">
                    Automatic Practice may open this if risk checks clear.
                  </p>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

      <section className="panel rise" aria-label="Founder feedback">
        <h2 style={{ marginTop: 0 }}>Founder feedback</h2>
        <p className="muted-note">
          Feedback is stored with the paper trade for later review. It never
          automatically changes live trading parameters.
        </p>
        <div className="feedback-form">
          <label>
            Asset
            <input
              value={feedbackSymbol}
              onChange={(e) => setFeedbackSymbol(e.target.value.toUpperCase())}
            />
          </label>
          <label>
            Feedback
            <select
              value={feedbackCode}
              onChange={(e) => setFeedbackCode(e.target.value)}
            >
              {FEEDBACK_OPTIONS.map((o) => (
                <option key={o.code} value={o.code}>
                  {o.label}
                </option>
              ))}
            </select>
          </label>
          <label>
            Note
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Optional"
            />
          </label>
          <button
            type="button"
            className="btn"
            disabled={pending}
            onClick={() => {
              startTransition(async () => {
                const closed = closedTrades.find((t) => t.symbol === feedbackSymbol);
                const res = await recordTrainingFeedbackAction({
                  portfolioId,
                  feedbackCode,
                  symbol: feedbackSymbol,
                  fillId: closed?.fill_id,
                  note: note || undefined,
                });
                setMessage(res.message);
                router.refresh();
              });
            }}
          >
            Save feedback
          </button>
        </div>
        {closedTrades.length > 0 ? (
          <div className="closed-lessons">
            <h3>After the trade</h3>
            <ul>
              {closedTrades.slice(0, 5).map((t) => (
                <li key={t.fill_id}>
                  {t.symbol}:{" "}
                  <span className={pnlClass(t.realized_pnl)}>
                    {moneyPnl(t.realized_pnl)}
                  </span>
                  {t.exit_reason ? ` — ${t.exit_reason}` : ""}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </section>

      <section className="panel rise" aria-label="Paper Training Scorecard">
        <h2 style={{ marginTop: 0 }}>Paper Training Scorecard</h2>
        {!scorecard ? (
          <p className="muted-note">Scorecard unavailable.</p>
        ) : (
          <>
            <div className="summary-grid summary-grid-primary">
              <div className="summary-card">
                <span className="metric-label">Paper trades completed</span>
                <strong>{scorecard.paper_trades_completed}</strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">Win rate</span>
                <strong>
                  {scorecard.win_rate != null
                    ? `${(Number(scorecard.win_rate) * 100).toFixed(0)}%`
                    : "—"}
                </strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">Total paper profit or loss</span>
                <strong className={pnlClass(scorecard.total_paper_pnl)}>
                  {moneyPnl(scorecard.total_paper_pnl)}
                </strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">Average win</span>
                <strong>
                  {scorecard.average_win != null
                    ? moneyPnl(scorecard.average_win)
                    : "—"}
                </strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">Average loss</span>
                <strong>
                  {scorecard.average_loss != null
                    ? moneyPnl(scorecard.average_loss)
                    : "—"}
                </strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">Profit factor</span>
                <strong>
                  {scorecard.profit_factor != null
                    ? Number(scorecard.profit_factor).toFixed(2)
                    : "—"}
                </strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">Maximum drawdown</span>
                <strong>
                  {scorecard.maximum_drawdown != null
                    ? money(scorecard.maximum_drawdown)
                    : "—"}
                </strong>
              </div>
              <div className="summary-card">
                <span className="metric-label">Trades with Founder feedback</span>
                <strong>{scorecard.trades_with_founder_feedback}</strong>
              </div>
            </div>
            <div className="readiness-box">
              <div className="metric-label">Live Readiness</div>
              <strong>{scorecard.live_readiness}</strong>
              <p>{scorecard.live_readiness_detail}</p>
              <p className="muted-note">{scorecard.disclaimer}</p>
            </div>
          </>
        )}
      </section>

      {message ? (
        <p className="control-feedback ok" role="status">
          {message}
        </p>
      ) : null}
    </div>
  );
}
