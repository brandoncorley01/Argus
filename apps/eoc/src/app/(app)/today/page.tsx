import type { Metadata } from "next";
import Link from "next/link";

import { ControlBar } from "@/components/founder/ControlBar";
import { EndDayButton } from "@/components/founder/EndDayButton";
import { EmptyState, Panel, StatusBadge } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import {
  deriveStatus,
  direction,
  firstName,
  greeting,
  money,
  pnlClass,
} from "@/lib/founder/simple";
import { apiFetch } from "@/lib/server/api";
import { ARGUS_UI_BUILD } from "@/lib/build";
import {
  getMicroLiveStatus,
  getProcessReady,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Home" };

type Portfolio = {
  id: string;
  name: string;
  cash_balance: string;
  kill_switch_active: boolean;
};

type Position = {
  symbol: string;
  quantity: string;
  unrealized_pnl?: string | null;
  realized_pnl?: string | null;
};

type DailyReport = {
  report_date: string;
  content?: { daily_pnl?: string | null; trade_count?: number };
};

export default async function TodayPage() {
  const user = await requireUser();
  const name = firstName(user.username);

  const [ready, microLive, portfolios, reports] = await Promise.all([
    soft(getProcessReady),
    soft(getMicroLiveStatus),
    soft(() => apiFetch<Portfolio[]>("/api/v1/paper/portfolios")),
    soft(() =>
      apiFetch<DailyReport[]>("/api/v1/operations/daily-reports", {
        searchParams: { limit: 1 },
      }),
    ),
  ]);

  const portfolio = portfolios?.[0] ?? null;
  let positions: Position[] = [];
  if (portfolio) {
    positions =
      (await soft(() =>
        apiFetch<Position[]>(`/api/v1/paper/portfolios/${portfolio.id}/positions`),
      )) ?? [];
  }
  const open = positions.filter((p) => Number(p.quantity) !== 0);

  // Home status tracks Start/Stop + Paper only.
  const status = deriveStatus({
    apiReady: ready != null,
    paperPaused: Boolean(portfolio?.kill_switch_active),
  });

  const liveLocked =
    microLive?.live_execution_active === false ||
    microLive?.activation_state === "PAPER_ONLY" ||
    microLive == null;

  const pnl = reports?.[0]?.content?.daily_pnl ?? null;

  return (
    <div className="founder-home">
      <header className="page-header rise">
        <div>
          <h1>{greeting(name)}</h1>
          <p>Start and stop Argus here.</p>
        </div>
      </header>

      <ControlBar status={status} buildId={ARGUS_UI_BUILD} />

      <div className="simple-row">
        <div className="simple-chip">
          <span className="metric-label">Paper</span>
          <StatusBadge
            status={portfolio?.kill_switch_active ? "degraded" : ready ? "healthy" : null}
            label={portfolio?.kill_switch_active ? "Paused" : ready ? "Active" : "Stopped"}
          />
        </div>
        <div className="simple-chip">
          <span className="metric-label">Live</span>
          <StatusBadge status={null} label={liveLocked ? "Locked" : "Check Advanced"} />
        </div>
        <div className="simple-chip">
          <span className="metric-label">Today&apos;s P&amp;L</span>
          <strong className={pnlClass(pnl)}>{money(pnl)}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Open positions</span>
          <strong>{open.length}</strong>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Open positions">
          {open.length === 0 ? (
            <EmptyState>No open positions.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>P&amp;L</th>
                  </tr>
                </thead>
                <tbody>
                  {open.slice(0, 5).map((p) => (
                    <tr key={p.symbol}>
                      <td>{p.symbol}</td>
                      <td>{direction(p.quantity)}</td>
                      <td className={pnlClass(p.unrealized_pnl ?? p.realized_pnl)}>
                        {money(p.unrealized_pnl ?? p.realized_pnl)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="form-actions" style={{ marginTop: "0.75rem" }}>
            <Link className="btn secondary" href="/trading">
              Trading
            </Link>
            <Link className="btn secondary" href="/portfolio">
              Portfolio
            </Link>
          </div>
        </Panel>

        <Panel title="End of day">
          <p style={{ color: "var(--ink-soft)", marginTop: 0 }}>
            Saves today&apos;s report and backup. Does not stop Argus.
          </p>
          <EndDayButton />
        </Panel>
      </div>

      <p className="muted-note" style={{ marginTop: "1.5rem" }}>
        UI build: {ARGUS_UI_BUILD}
      </p>
    </div>
  );
}
