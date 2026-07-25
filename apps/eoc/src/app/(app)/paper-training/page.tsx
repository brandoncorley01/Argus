import type { Metadata } from "next";
import Link from "next/link";

import { PaperTrainingClient } from "@/components/founder/PaperTrainingClient";
import { EmptyState } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { ARGUS_UI_BUILD } from "@/lib/build";
import { apiFetch } from "@/lib/server/api";
import { soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Paper Training" };

type Portfolio = { id: string; name: string };
type Settings = { mode: "automatic" | "coaching"; default_notional: string };
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
  lesson?: Record<string, unknown> | null;
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
type Readiness = { next_step: string; ready: boolean; symbol: string | null };

export default async function PaperTrainingPage() {
  await requireUser();
  const portfolios = await soft(() =>
    apiFetch<Portfolio[]>("/api/v1/paper/portfolios"),
  );
  const portfolio = portfolios?.[0] ?? null;
  if (!portfolio) {
    return (
      <div>
        <header className="page-header">
          <div>
            <h1>Paper Training</h1>
            <p>Safe interactive practice before real money.</p>
          </div>
        </header>
        <EmptyState>
          No paper portfolio yet. Create one under Advanced → Paper details, or
          Start Argus from a fresh install.
        </EmptyState>
      </div>
    );
  }

  const [settings, candidates, scorecard, closedTrades, readiness] =
    await Promise.all([
      soft(() =>
        apiFetch<Settings>(`/api/v1/paper/training/${portfolio.id}/settings`),
      ),
      soft(() =>
        apiFetch<Candidate[]>("/api/v1/paper/training/candidates", {
          searchParams: { limit: 12 },
        }),
      ),
      soft(() =>
        apiFetch<Scorecard>(
          `/api/v1/paper/training/${portfolio.id}/scorecard`,
        ),
      ),
      soft(() =>
        apiFetch<ClosedTrade[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/closed-trades`,
          { searchParams: { limit: 10 } },
        ),
      ),
      soft(() => apiFetch<Readiness[]>("/api/v1/paper/training/readiness")),
    ]);

  const notReady = (readiness ?? []).find((r) => !r.ready);

  return (
    <div>
      <header className="page-header rise">
        <div>
          <h1>Paper Training</h1>
          <p>
            Argus Training Lab — watch, guide, test, and evaluate with simulated
            money only. Build: {ARGUS_UI_BUILD}.{" "}
            <Link href="/today">Back to Home</Link>
          </p>
        </div>
      </header>
      <PaperTrainingClient
        portfolioId={portfolio.id}
        mode={settings?.mode ?? "coaching"}
        defaultNotional={settings?.default_notional ?? "100"}
        candidates={candidates ?? []}
        scorecard={scorecard}
        closedTrades={closedTrades ?? []}
        readinessNextStep={notReady?.next_step ?? null}
      />
    </div>
  );
}
