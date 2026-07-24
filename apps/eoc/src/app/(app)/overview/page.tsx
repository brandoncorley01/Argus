import type { Metadata } from "next";
import Link from "next/link";

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
import { isFounder, isOperator, primaryRole, roleLabel } from "@/lib/rbac";
import { apiFetch } from "@/lib/server/api";
import {
  getIncidents,
  getInstitutionalHealth,
  getMicroLiveStatus,
  getOperatingMode,
  getProcessReady,
  getProtectiveActions,
  getServices,
  getWorkerInstances,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Executive Overview" };

type SystemHealth = {
  overall_status: string;
  paper?: {
    default_provider_key: string | null;
    default_provider_is_internal_paper: boolean;
    active_kill_switch_count: number;
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
    occurred_at?: string | null;
  }>;
  incident_history?: Array<{
    id: string;
    title: string;
    severity: string;
    status: string;
    opened_at?: string | null;
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

export default async function OverviewPage() {
  const user = await requireUser();
  const role = primaryRole(user);

  const [
    mode,
    health,
    ready,
    services,
    incidents,
    protective,
    workers,
    microLive,
    systemHealth,
    providers,
    portfolios,
    dailyReports,
  ] = await Promise.all([
    soft(getOperatingMode),
    soft(getInstitutionalHealth),
    soft(getProcessReady),
    soft(getServices),
    soft(getIncidents),
    soft(getProtectiveActions),
    soft(getWorkerInstances),
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
      .length ?? null;

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

  let openPositions: PaperPosition[] | null = null;
  if (portfolios && portfolios.length > 0) {
    const first = portfolios[0];
    openPositions = await soft(() =>
      apiFetch<PaperPosition[]>(`/api/v1/paper/portfolios/${first.id}/positions`),
    );
  }

  const workerCount = workers?.length ?? systemHealth?.worker_instances?.length ?? null;
  const overallHealth =
    systemHealth?.overall_status ?? health?.status ?? (ready ? "ready" : null);

  const paperStatus = portfolios
    ? portfolios.some((p) => p.kill_switch_active)
      ? "kill switch active"
      : `${portfolios.length} portfolio(s)`
    : "unavailable";

  const uptimeSec = systemHealth?.uptime_seconds;
  const uptimeLabel =
    uptimeSec == null
      ? "—"
      : `${Math.floor(uptimeSec / 3600)}h ${Math.floor((uptimeSec % 3600) / 60)}m`;
  const activeAlertCount = systemHealth?.active_alerts?.length ?? openIncidents;
  const lastBackup = systemHealth?.backup?.available
    ? formatTimestamp(systemHealth.backup.completed_at ?? null)
    : systemHealth?.backup?.note ?? "none";

  const dashboardTitle =
    role === "FOUNDER"
      ? "Founder dashboard"
      : role === "OPERATOR"
        ? "Operator dashboard"
        : "Viewer dashboard";

  return (
    <>
      <PageHeader
        title={dashboardTitle}
        description={`Signed in as ${user.username} (${roleLabel(role)}). Live control-plane reads only — empty means unavailable, not a fabricated zero.`}
      />

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
            hint="System health / institutional projection"
          />
        </Panel>
        <Panel className="rise-delay-1">
          <Metric
            label="Paper trading"
            value={paperStatus}
            hint={
              systemHealth?.paper?.last_paper_order_at
                ? `Last trade ${formatTimestamp(systemHealth.paper.last_paper_order_at)}`
                : "Internal paper books"
            }
          />
        </Panel>
        <Panel className="rise-delay-2">
          <Metric
            label="Provider"
            value={providerLabel}
            hint={
              providerIsPaper
                ? "internal_paper · certified paper path"
                : "Check default provider registry"
            }
          />
        </Panel>
        <Panel className="rise-delay-2">
          <Metric
            label="Live trading"
            value={liveDisabled ? "Disabled" : "Check status"}
            hint={
              microLive
                ? `activation=${microLive.activation_state}`
                : "Not certified · deny-by-default"
            }
          />
        </Panel>
      </div>

      <div className="grid grid-4" style={{ marginBottom: "1rem" }}>
        <Panel>
          <Metric
            label="Workers"
            value={workerCount === null ? "—" : workerCount}
            hint="Registered worker instances"
          />
        </Panel>
        <Panel>
          <Metric
            label="Today's P&L"
            value={todayPnl ?? "—"}
            hint={
              todayPnl != null
                ? `Paper daily report${todayTrades != null ? ` · ${todayTrades} fills` : ""}`
                : "No daily report yet (paper only when generated)"
            }
          />
        </Panel>
        <Panel>
          <Metric
            label="Open positions"
            value={
              openPositions == null
                ? "—"
                : openPositions.filter((p) => Number(p.quantity) !== 0).length
            }
            hint={
              portfolios?.[0]
                ? `From portfolio ${portfolios[0].name}`
                : "No portfolios"
            }
          />
        </Panel>
        <Panel>
          <Metric
            label="Active alerts"
            value={activeAlertCount === null ? "—" : activeAlertCount}
            hint="Critical/high ops events + open incidents"
          />
        </Panel>
      </div>

      <div className="grid grid-4" style={{ marginBottom: "1rem" }}>
        <Panel>
          <Metric
            label="Runtime uptime"
            value={uptimeLabel}
            hint="API process uptime"
          />
        </Panel>
        <Panel>
          <Metric
            label="Last restart"
            value={formatTimestamp(systemHealth?.process_started_at ?? null)}
            hint="API process start time"
          />
        </Panel>
        <Panel>
          <Metric
            label="Last backup"
            value={lastBackup}
            hint={
              systemHealth?.backup?.integrity_ok === false
                ? "Integrity failed"
                : systemHealth?.backup?.integrity_ok
                  ? "Integrity verified"
                  : "From backups/LAST_OK.json"
            }
          />
        </Panel>
        <Panel>
          <Metric
            label="Alerts"
            value={openIncidents === null ? "—" : openIncidents}
            hint="Open + investigating incidents"
          />
        </Panel>
      </div>

      <div className="grid grid-2">
        <Panel title="Executive summary" className="rise-delay-3">
          <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--ink-soft)" }}>
            <li>
              Role surface: {roleLabel(role)}. Mutations require matching backend
              authority; this UI never elevates privileges.
            </li>
            <li>
              Operating mode: {mode?.current_mode ?? "unavailable"} · Emergency
              stop:{" "}
              {mode
                ? mode.emergency_stop_active
                  ? "ACTIVE"
                  : "inactive"
                : "unknown"}
            </li>
            <li>
              API readiness: {ready ? "ready" : "unavailable"} · Services:{" "}
              {services ? services.length : "unavailable"}
            </li>
            <li>
              Protective recommendations:{" "}
              {protective ? protective.length : "unavailable"}
            </li>
          </ul>
          <div className="form-actions" style={{ marginTop: "1rem" }}>
            <Link className="btn" href="/system-health">
              System Health
            </Link>
            <Link className="btn secondary" href="/paper">
              Paper Trading
            </Link>
            {isOperator(user) ? (
              <Link className="btn secondary" href="/operations">
                Operating mode
              </Link>
            ) : null}
            <Link className="btn secondary" href="/incidents">
              Incidents
            </Link>
            {isFounder(user) ? (
              <Link className="btn secondary" href="/administration">
                Administration
              </Link>
            ) : null}
          </div>
        </Panel>

        <Panel title="Open positions (sample book)">
          {!portfolios ? (
            <ErrorState>Paper portfolios unavailable.</ErrorState>
          ) : !openPositions ? (
            <EmptyState>No position data for the first portfolio.</EmptyState>
          ) : openPositions.filter((p) => Number(p.quantity) !== 0).length === 0 ? (
            <EmptyState>No open positions.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Realized</th>
                  </tr>
                </thead>
                <tbody>
                  {openPositions
                    .filter((p) => Number(p.quantity) !== 0)
                    .slice(0, 8)
                    .map((p) => (
                      <tr key={p.symbol}>
                        <td>{p.symbol}</td>
                        <td>{p.quantity}</td>
                        <td>{p.realized_pnl ?? "—"}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Runtime monitor">
          {!systemHealth?.runtime_monitor ? (
            <EmptyState>Runtime monitor unavailable.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Component</th>
                    <th>Status</th>
                    <th>Detail</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(systemHealth.runtime_monitor).map(([key, probe]) => (
                    <tr key={key}>
                      <td>{key}</td>
                      <td>
                        <StatusBadge status={probe.status} label={probe.status} />
                      </td>
                      <td>{probe.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Active alerts">
          {!systemHealth?.active_alerts ? (
            <EmptyState>Alert feed unavailable.</EmptyState>
          ) : systemHealth.active_alerts.length === 0 ? (
            <EmptyState>No active critical/high alerts.</EmptyState>
          ) : (
            <ul style={{ margin: 0, paddingLeft: "1.1rem", color: "var(--ink-soft)" }}>
              {systemHealth.active_alerts.slice(0, 8).map((a, idx) => (
                <li key={`${a.kind}-${idx}`}>
                  [{a.severity}] {a.description}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Incident history">
          {!systemHealth?.incident_history ? (
            <EmptyState>Incident history unavailable.</EmptyState>
          ) : systemHealth.incident_history.length === 0 ? (
            <EmptyState>No incidents recorded.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Opened</th>
                  </tr>
                </thead>
                <tbody>
                  {systemHealth.incident_history.slice(0, 8).map((row) => (
                    <tr key={row.id}>
                      <td>
                        <Link href={`/incidents/${row.id}`}>{row.title}</Link>
                      </td>
                      <td>{row.severity}</td>
                      <td>{row.status}</td>
                      <td>{formatTimestamp(row.opened_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="form-actions" style={{ marginTop: "0.75rem" }}>
            <Link className="btn secondary" href="/incidents">
              All incidents
            </Link>
          </div>
        </Panel>

        <Panel title="Service snapshot">
          {!services ? (
            <ErrorState>Service health list unavailable.</ErrorState>
          ) : services.length === 0 ? (
            <EmptyState>No registered services returned.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Kind</th>
                    <th>Status</th>
                    <th>Last observed</th>
                  </tr>
                </thead>
                <tbody>
                  {services.slice(0, 8).map((row) => (
                    <tr key={row.service.id}>
                      <td>{row.service.display_name}</td>
                      <td>{row.service.service_kind}</td>
                      <td>
                        <StatusBadge
                          status={row.projection?.status}
                          label={row.projection?.status ?? "no projection"}
                        />
                      </td>
                      <td>
                        {formatTimestamp(row.projection?.last_observed_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </>
  );
}
