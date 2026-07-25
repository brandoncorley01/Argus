"use client";

import Link from "next/link";
import { useState } from "react";

import { EmptyState } from "@/components/ui";
import {
  decisionLabel,
  outlookLabel,
  plainRejection,
} from "@/lib/founder/plainLanguage";
import { money } from "@/lib/founder/simple";

export type ScanCandidate = {
  id: string;
  symbol: string;
  bias: string;
  stage: string;
  score: string;
  reason_code: string | null;
  reason_text: string | null;
  current_price: string | null;
  entry_zone: string | null;
  stop_loss: string | null;
  take_profit: string | null;
  risk_status: string;
  timeframe: string;
  strategy_key: string;
  evaluated_at: string;
};

function Tip({ text }: { text: string }) {
  return (
    <span className="info-tip" title={text} aria-label={text}>
      ?
    </span>
  );
}

function confidence(score: string): string {
  const n = Number(score);
  if (!Number.isFinite(n)) return "Low";
  if (n >= 80) return "High";
  if (n >= 50) return "Medium";
  return "Low";
}

function waitingFor(c: ScanCandidate): string {
  if (c.stage === "Rejected") return "Nothing — this idea was skipped.";
  if (c.reason_code === "insufficient_history") return "More recent price history.";
  if (c.stage === "Watching")
    return "One more confirming price update before a paper entry is considered.";
  if (c.stage === "Risk Review") return "Risk checks or Founder coaching approval.";
  return "Argus is still evaluating.";
}

export function ConsideringTrades({
  candidates,
  portfolioId,
  defaultNotional,
}: {
  candidates: ScanCandidate[];
  portfolioId: string | null;
  defaultNotional?: string;
}) {
  const [openTech, setOpenTech] = useState<string | null>(null);

  if (candidates.length === 0) {
    return (
      <EmptyState>
        No trade ideas yet. Refresh recent prices, then scan markets. Argus will
        list ideas here when something meets your rules.
      </EmptyState>
    );
  }

  return (
    <div className="considering-list">
      {candidates.map((c) => {
        const decision = decisionLabel(c.stage);
        const why = plainRejection(c.reason_code, c.reason_text);
        const showTech = openTech === c.id;
        return (
          <article key={c.id} className="considering-card">
            <header className="considering-card-head">
              <h3>{c.symbol}</h3>
              <span className={`decision-pill decision-${decision.toLowerCase()}`}>
                {decision}
              </span>
            </header>
            <dl className="considering-dl">
              <div>
                <dt>Argus outlook</dt>
                <dd>{outlookLabel(c.bias)}</dd>
              </div>
              <div>
                <dt>Current price</dt>
                <dd>{c.current_price ? money(c.current_price) : "Unavailable"}</dd>
              </div>
              <div>
                <dt>Confidence</dt>
                <dd>{confidence(c.score)}</dd>
              </div>
              <div>
                <dt>
                  Proposed paper investment{" "}
                  <Tip text="Simulated dollar size Argus would risk in paper practice." />
                </dt>
                <dd>{money(defaultNotional ?? "100")}</dd>
              </div>
              <div>
                <dt>Maximum planned loss</dt>
                <dd>{c.stop_loss ? money(c.stop_loss) : "Not set"}</dd>
              </div>
              <div>
                <dt>Potential profit target</dt>
                <dd>{c.take_profit ? money(c.take_profit) : "Not set"}</dd>
              </div>
            </dl>
            <p>
              <strong>Why Argus noticed it:</strong> {why}
            </p>
            <p>
              <strong>What confirmation Argus is waiting for:</strong>{" "}
              {waitingFor(c)}
            </p>
            <button
              type="button"
              className="btn secondary"
              onClick={() => setOpenTech(showTech ? null : c.id)}
            >
              {showTech ? "Hide technical details" : "View technical details"}
            </button>
            {showTech ? (
              <pre className="tech-details">
                {JSON.stringify(
                  {
                    stage: c.stage,
                    score: c.score,
                    reason_code: c.reason_code,
                    risk_status: c.risk_status,
                    timeframe: c.timeframe,
                    strategy_key: c.strategy_key,
                    entry_zone: c.entry_zone,
                  },
                  null,
                  2,
                )}
              </pre>
            ) : null}
            {portfolioId ? (
              <p className="muted-note">
                Coach Take / Skip on{" "}
                <Link href="/paper-training">Paper Training</Link>.
              </p>
            ) : null}
          </article>
        );
      })}
    </div>
  );
}
