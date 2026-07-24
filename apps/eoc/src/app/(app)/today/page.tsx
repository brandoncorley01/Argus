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
import { formatTimestamp } from "@/lib/format";
import { apiFetch } from "@/lib/server/api";
import {
  getIncidents,
  getMicroLiveStatus,
  getProcessReady,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Today" };

type SystemHealth = {
  overall_status: string;
  active_alerts?: Array<{ severity: string; description: string }>;
  runtime_monitor?: Record<string, { status: string; detail: string }>;
  backup?: { available: boolean; integrity_ok?: boolean | null; completed_at?: string | null };
  worker_instances?: Array<{ status: string }>;
  process_started_at?: string;
  generated_at?: string;
};

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
  average_cost?: string;
};

type DailyReport = {
  report_date: string;
  content?: { daily_pnl?: string | null; trade_count?: number };
};

export default async function TodayPage() {
  const user = await requireUser();
  const name = firstName(user.username);

  const [ready, incidents, microLive, health, portfolios, reports] = await Promise.all([
    soft(getProcessReady),
    soft(getIncidents),
    soft(getMicroLiveStatus),
    soft(() => apiFetch<SystemHealth>("/api/v1/operations/system-health")),
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

  const openIncidents =
    incidents?.filter((i) => i.status === "open" || i.status === "investigating")
      .length ?? 0;
  const criticalAlerts =
    (health?.active_alerts ?? []).filter(
      (a) => a.severity === "critical" || a.severity === "high",
    ).length + openIncidents;
  const workerFailed = Object.entries(health?.runtime_monitor ?? {}).some(
    ([k, v]) => (k === "worker" || k === "api") && v.status === "failed",
  );

  const status = deriveStatus({
    apiReady: ready == null ? false : true,
    paperPaused: Boolean(portfolio?.kill_switch_active),
    criticalAlerts,
    workerFailed,
  });

  const liveLocked =
    microLive?.live_execution_active === false ||
    microLive?.activation_state === "PAPER_ONLY" ||
    microLive == null;

  const pnl = reports?.[0]?.content?.daily_pnl ?? null;
  const reportDate = reports?.[0]?.report_date;
  const cash = portfolio ? Number(portfolio.cash_balance) : NaN;
  const deployed = open.reduce((s, p) => {
    const qty = Math.abs(Number(p.quantity) || 0);
    const cost = Number(p.average_cost) || 0;
    return s + qty * cost;
  }, 0);
  const unrealized = open.reduce((s, p) => s + (Number(p.unrealized_pnl) || 0), 0);
  const portfolioValue =
    Number.isFinite(cash) ? cash + deployed + unrealized : null;

  const attention: string[] = [];
  if (ready == null) attention.push("Argus looks stopped — press Start Argus.");
  if (portfolio?.kill_switch_active) attention.push("Paper trading is paused.");
  if (workerFailed) attention.push("A background service needs attention — try Restart.");
  if (health?.backup?.integrity_ok === false) {
    attention.push("Last backup failed — press Backup.");
  }
  if (criticalAlerts > 0) attention.push("There are unresolved alerts.");

  return (
    <div className="founder-home">
      <header className="page-header rise">
        <div>
          <h1>{greeting(name)}.</h1>
          <p>Start and Stop Argus here. Everything else is secondary.</p>
        </div>
      </header>

      {/* Start / Stop are intentionally first — above summary cards */}
      <ControlBar status={status} />

      <div className="simple-row">
        <div className="simple-chip">
          <span className="metric-label">Argus</span>
          <StatusBadge
            status={
              status === "Running" ? "healthy" : status === "Stopped" ? "unhealthy" : "degraded"
            }
            label={
              status === "Running"
                ? "Running"
                : status === "Stopped"
                  ? "Stopped"
                  : "Attention needed"
            }
          />
        </div>
        <div className="simple-chip">
          <span className="metric-label">Paper trading</span>
          <StatusBadge
            status={portfolio?.kill_switch_active ? "degraded" : ready ? "healthy" : null}
            label={portfolio?.kill_switch_active ? "Paused" : ready ? "Active" : "Unavailable"}
          />
        </div>
        <div className="simple-chip">
          <span className="metric-label">Live trading</span>
          <StatusBadge status={null} label={liveLocked ? "Locked" : "Check Advanced"} />
        </div>
        <div className="simple-chip">
          <span className="metric-label">Last updated</span>
          <strong>
            {formatTimestamp(health?.generated_at ?? health?.process_started_at ?? null)}
          </strong>
        </div>
      </div>

      <div className="simple-row" style={{ marginTop: "0.75rem" }}>
        <div className="simple-chip">
          <span className="metric-label">Today&apos;s P&amp;L</span>
          <strong className={pnlClass(pnl)}>{money(pnl)}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Portfolio value</span>
          <strong>{portfolioValue == null ? "Unavailable" : money(portfolioValue)}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Open positions</span>
          <strong>{open.length}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Paper cash</span>
          <strong>{portfolio ? money(portfolio.cash_balance) : "Unavailable"}</strong>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Do I need to do anything?">
          {attention.length === 0 ? (
            <p className="attention-ok">All clear. No action needed.</p>
          ) : (
            <ul className="plain-list attention-needed">
              {attention.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
          )}
          {(health?.active_alerts ?? []).slice(0, 3).map((a, i) => (
            <p key={i} style={{ color: "var(--ink-soft)", fontSize: "0.9rem" }}>
              <StatusBadge status={a.severity} label={a.severity} /> {a.description}
            </p>
          ))}
          {pnl == null ? (
            <p className="muted-note" style={{ marginTop: "0.75rem" }}>
              No daily report yet
              {reportDate ? ` (latest on file: ${reportDate})` : ""}. Use End Trading Day
              when you finish.
            </p>
          ) : null}
        </Panel>

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
              Review trading
            </Link>
            <Link className="btn secondary" href="/portfolio">
              Portfolio
            </Link>
          </div>
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="End of day">
          <p style={{ color: "var(--ink-soft)", marginTop: 0 }}>
            Creates or confirms today&apos;s report, then runs backup. Does not stop Argus
            and does not close positions.
          </p>
          <EndDayButton />
        </Panel>
      </div>
    </div>
  );
}
