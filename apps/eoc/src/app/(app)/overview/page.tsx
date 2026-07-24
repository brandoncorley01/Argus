import type { Metadata } from "next";
import Link from "next/link";

import { GenerateDailyReportForm } from "@/components/GenerateDailyReportForm";
import {
  EmptyState,
  ErrorState,
  Metric,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import {
  FOUNDER_MILESTONE,
  milestoneProgressPercent,
} from "@/lib/milestone";
import { isFounder, isOperator, primaryRole, roleLabel } from "@/lib/rbac";
import { apiFetch } from "@/lib/server/api";
import {
  getIncidents,
  getMicroLiveStatus,
  getOperatingMode,
  getProcessReady,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Founder Dashboard" };

type SystemHealth = {
  overall_status: string;
  paper?: {
    default_provider_key: string | null;
    default_provider_is_internal_paper: boolean;
    last_paper_order_at: string | null;
  };
  worker_instances?: Array<{ instance_key: string; status: string }>;
  uptime_seconds?: number;
  process_started_at?: string;
  backup?: {
    available: boolean;
    completed_at?: string | null;
    integrity_ok?: boolean | null;
    note?: string | null;
  };
  active_alerts?: Array<{
    kind: string;
    severity: string;
    description: string;
  }>;
  runtime_monitor?: Record<string, { status: string; detail: string }>;
};

type PaperProviderRow = {
  provider: { provider_key: string; is_default: boolean; environment: string };
};

type PaperPortfolio = {
  id: string;
  name: string;
  cash_balance: string;
  status: string;
  kill_switch_active: boolean;
};

type PaperPosition = {
  symbol: string;
  quantity: string;
  unrealized_pnl?: string | null;
  realized_pnl?: string | null;
};

type DailyReport = {
  report_date: string;
  content?: { daily_pnl?: string | null; trade_count?: number };
};

function formatUptime(seconds: number | undefined): string {
  if (seconds == null) return "—";
  const s = Math.max(0, Math.floor(seconds));
  return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
}

export default async function OverviewPage() {
  const user = await requireUser();
  const role = primaryRole(user);
  const canGenerateReport = isFounder(user) || isOperator(user);

  const [
    mode,
    ready,
    incidents,
    microLive,
    systemHealth,
    providers,
    portfolios,
    dailyReports,
  ] = await Promise.all([
    soft(getOperatingMode),
    soft(getProcessReady),
    soft(getIncidents),
    soft(getMicroLiveStatus),
    soft(() => apiFetch<SystemHealth>("/api/v1/operations/system-health")),
    soft(() => apiFetch<PaperProviderRow[]>("/api/v1/paper/providers")),
    soft(() => apiFetch<PaperPortfolio[]>("/api/v1/paper/portfolios")),
    soft(() =>
      apiFetch<DailyReport[]>("/api/v1/operations/daily-reports", {
        searchParams: { limit: 1 },
      }),
    ),
  ]);

  const openIncidents =
    incidents?.filter((i) => i.status === "open" || i.status === "investigating")
      .length ?? 0;

  const defaultProvider =
    providers?.find((p) => p.provider.is_default)?.provider ?? null;
  const providerLabel =
    systemHealth?.paper?.default_provider_key ??
    defaultProvider?.provider_key ??
    "unavailable";
  const providerIsPaper =
    systemHealth?.paper?.default_provider_is_internal_paper ??
    defaultProvider?.provider_key === "internal_paper";

  const liveDisabled =
    microLive?.live_execution_active === false ||
    microLive?.activation_state === "PAPER_ONLY" ||
    microLive == null;

  const todayPnl = dailyReports?.[0]?.content?.daily_pnl ?? null;
  const todayTrades = dailyReports?.[0]?.content?.trade_count;
  const reportDate = dailyReports?.[0]?.report_date;

  const portfolio = portfolios?.[0] ?? null;
  let openPositions: PaperPosition[] | null = null;
  if (portfolio) {
    openPositions = await soft(() =>
      apiFetch<PaperPosition[]>(`/api/v1/paper/portfolios/${portfolio.id}/positions`),
    );
  }
  const openPositionRows =
    openPositions?.filter((p) => Number(p.quantity) !== 0) ?? [];

  const overallHealth = systemHealth?.overall_status ?? (ready ? "ready" : null);
  const activeAlerts = systemHealth?.active_alerts ?? [];
  const alertCount = Math.max(activeAlerts.length, openIncidents);
  const progress = milestoneProgressPercent();

  const monitorFailed = systemHealth?.runtime_monitor
    ? Object.values(systemHealth.runtime_monitor).filter((p) => p.status === "failed")
        .length
    : null;

  return (
    <>
      <PageHeader
        title={
          role === "FOUNDER"
            ? "Founder dashboard"
            : role === "OPERATOR"
              ? "Operator dashboard"
              : "Viewer dashboard"
        }
        description={`Signed in as ${user.username} (${roleLabel(role)}). Provider ${FOUNDER_MILESTONE.provider} · Live trading ${FOUNDER_MILESTONE.liveTrading}.`}
      />

      <Panel title="Current milestone" className="rise">
        <div style={{ marginBottom: "1rem" }}>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: "1rem",
              alignItems: "baseline",
              justifyContent: "space-between",
            }}
          >
          <div>
            <div style={{ fontSize: "1.15rem", fontWeight: 600 }}>
              {FOUNDER_MILESTONE.label}
            </div>
            <p style={{ margin: "0.35rem 0 0", color: "var(--ink-soft)" }}>
              {FOUNDER_MILESTONE.sprint} · Phases {FOUNDER_MILESTONE.phasesComplete}/
              {FOUNDER_MILESTONE.phasesTotal} complete · {FOUNDER_MILESTONE.note}
            </p>
          </div>
          <Metric
            label="Foundation progress"
            value={`${progress}%`}
            hint={`Phase ${FOUNDER_MILESTONE.phasesComplete + 1} planned`}
          />
          </div>
          <div
            role="progressbar"
            aria-valuenow={progress}
            aria-valuemin={0}
            aria-valuemax={100}
            style={{
              marginTop: "0.85rem",
              height: "0.45rem",
              borderRadius: "999px",
              background: "var(--line, #d8d4cc)",
              overflow: "hidden",
            }}
          >
            <div
              style={{
                width: `${progress}%`,
                height: "100%",
                background: "var(--accent, #2f5d50)",
              }}
            />
          </div>
        </div>
      </Panel>

      <div className="grid grid-4" style={{ marginBottom: "1rem" }}>
        <Panel className="rise-delay-1">
          <Metric
            label="Overall health"
            value={
              overallHealth ? (
                <StatusBadge status={overallHealth} />
              ) : (
                <StatusBadge status={null} label="unavailable" />
              )
            }
            hint={
              monitorFailed != null
                ? `${monitorFailed} runtime probe(s) failed`
                : "Institutional / system health"
            }
          />
        </Panel>
        <Panel className="rise-delay-1">
          <Metric
            label="Portfolio summary"
            value={
              portfolio
                ? portfolio.kill_switch_active
                  ? "Kill switch"
                  : portfolio.cash_balance
                : "—"
            }
            hint={
              portfolio
                ? `${portfolio.name} · ${portfolio.status} · ${openPositionRows.length} open`
                : "No paper portfolios"
            }
          />
        </Panel>
        <Panel className="rise-delay-2">
          <Metric
            label="Paper P&L"
            value={todayPnl ?? "—"}
            hint={
              todayPnl != null
                ? `Report date ${reportDate ?? ""}${todayTrades != null ? ` · ${todayTrades} fills` : ""}`
                : "From latest daily paper report (not live)"
            }
          />
        </Panel>
        <Panel className="rise-delay-2">
          <Metric
            label="Active alerts"
            value={alertCount}
            hint={
              openIncidents
                ? `${openIncidents} open/investigating incident(s)`
                : "Critical/high ops + incidents"
            }
          />
        </Panel>
      </div>

      <div className="grid grid-4" style={{ marginBottom: "1rem" }}>
        <Panel>
          <Metric
            label="Open positions"
            value={openPositions == null ? "—" : openPositionRows.length}
            hint={portfolio ? portfolio.name : "No book selected"}
          />
        </Panel>
        <Panel>
          <Metric
            label="Provider"
            value={providerLabel}
            hint={providerIsPaper ? "Certified paper path" : "Check registry"}
          />
        </Panel>
        <Panel>
          <Metric
            label="Live trading"
            value={liveDisabled ? "Disabled" : "Check status"}
            hint={
              microLive
                ? `activation=${microLive.activation_state}`
                : "Deny-by-default"
            }
          />
        </Panel>
        <Panel>
          <Metric
            label="Uptime / backup"
            value={formatUptime(systemHealth?.uptime_seconds)}
            hint={
              systemHealth?.backup?.available
                ? `Last backup ${formatTimestamp(systemHealth.backup.completed_at ?? null)}`
                : systemHealth?.backup?.note ?? "No verified backup yet"
            }
          />
        </Panel>
      </div>

      <div className="grid grid-2">
        <Panel title="Open positions" className="rise-delay-3">
          {!portfolios ? (
            <ErrorState>Paper portfolios unavailable.</ErrorState>
          ) : !portfolio ? (
            <EmptyState>No portfolios. Create one under Paper Trading.</EmptyState>
          ) : openPositions == null ? (
            <EmptyState>Position data unavailable.</EmptyState>
          ) : openPositionRows.length === 0 ? (
            <EmptyState>No open positions.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Unrealized</th>
                    <th>Realized</th>
                  </tr>
                </thead>
                <tbody>
                  {openPositionRows.slice(0, 12).map((p) => (
                    <tr key={p.symbol}>
                      <td>{p.symbol}</td>
                      <td>{p.quantity}</td>
                      <td>{p.unrealized_pnl ?? "—"}</td>
                      <td>{p.realized_pnl ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="form-actions" style={{ marginTop: "0.75rem" }}>
            <Link className="btn secondary" href="/paper">
              Paper Trading
            </Link>
          </div>
        </Panel>

        <Panel title="Active alerts" className="rise-delay-3">
          {activeAlerts.length === 0 && openIncidents === 0 ? (
            <EmptyState>No active critical/high alerts.</EmptyState>
          ) : (
            <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--ink-soft)" }}>
              {activeAlerts.slice(0, 8).map((a, idx) => (
                <li key={`${a.kind}-${idx}`}>
                  [{a.severity}] {a.description}
                </li>
              ))}
              {activeAlerts.length === 0 && openIncidents > 0 ? (
                <li>
                  {openIncidents} open/investigating incident(s) — see Incidents.
                </li>
              ) : null}
            </ul>
          )}
          <div className="form-actions" style={{ marginTop: "0.75rem" }}>
            <Link className="btn secondary" href="/incidents">
              Incidents
            </Link>
            <Link className="btn secondary" href="/system-health">
              System Health
            </Link>
          </div>
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Operating snapshot">
          <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--ink-soft)" }}>
            <li>
              Mode: {mode?.current_mode ?? "unavailable"} · Emergency stop:{" "}
              {mode
                ? mode.emergency_stop_active
                  ? "ACTIVE"
                  : "inactive"
                : "unknown"}
            </li>
            <li>
              API: {ready ? "ready" : "unavailable"} · Workers:{" "}
              {systemHealth?.worker_instances?.length ?? "—"} · Last restart:{" "}
              {formatTimestamp(systemHealth?.process_started_at ?? null)}
            </li>
            <li>
              Backup integrity:{" "}
              {systemHealth?.backup?.integrity_ok == null
                ? "unknown"
                : systemHealth.backup.integrity_ok
                  ? "ok"
                  : "failed"}
            </li>
          </ul>
          <div className="form-actions" style={{ marginTop: "1rem" }}>
            <Link className="btn" href="/system-health">
              System Health
            </Link>
            {isOperator(user) ? (
              <Link className="btn secondary" href="/operations">
                Operating mode
              </Link>
            ) : null}
            {isFounder(user) ? (
              <Link className="btn secondary" href="/administration">
                Administration
              </Link>
            ) : null}
          </div>
        </Panel>

        <Panel title="Daily paper report">
          {canGenerateReport ? (
            <GenerateDailyReportForm />
          ) : (
            <EmptyState>
              Report generation requires Founder or Operator authority.
            </EmptyState>
          )}
        </Panel>
      </div>
    </>
  );
}
