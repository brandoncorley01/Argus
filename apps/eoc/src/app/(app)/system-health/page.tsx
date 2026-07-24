import type { Metadata } from "next";

import { GenerateDailyReportForm } from "@/components/GenerateDailyReportForm";
import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
  StatusBadge,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { apiFetch } from "@/lib/server/api";
import { soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "System Health" };

type SystemHealth = {
  overall_status: string;
  app_name: string;
  healthy_service_count: number;
  warning_service_count: number;
  critical_service_count: number;
  readiness: { postgres?: boolean; redis?: boolean };
  host: {
    captured_at: string;
    cpu_percent: number;
    memory_percent: number;
    disk_percent: number;
  } | null;
  paper: {
    default_provider_key: string | null;
    default_provider_is_internal_paper: boolean;
    active_kill_switch_count: number;
    last_paper_order_at: string | null;
  };
  reconciliation: {
    available: boolean;
    started_at?: string;
    status?: string;
    note?: string;
  };
  incidents_by_severity: Record<string, number>;
  worker_instances: Array<{
    instance_key: string;
    status: string;
    last_seen_at: string;
  }>;
  uptime_seconds: number;
  process_started_at: string;
  recent_events: Array<{
    occurred_at: string;
    component: string;
    severity: string;
    description: string;
    correlation_id: string;
  }>;
  services: Array<{
    service_key: string;
    display_name: string;
    status: string;
  }>;
  generated_at: string;
  runtime_monitor?: Record<string, { status: string; detail: string }>;
  backup?: {
    available: boolean;
    completed_at?: string | null;
    integrity_ok?: boolean | null;
    filename?: string | null;
    note?: string | null;
  };
  active_alerts?: Array<{
    kind: string;
    severity: string;
    description: string;
  }>;
  incident_history?: Array<{
    id: string;
    title: string;
    severity: string;
    status: string;
    opened_at?: string | null;
  }>;
};

type DailyReport = {
  id: string;
  report_date: string;
  content_hash: string;
  generated_at: string;
  is_immutable: boolean;
  content: {
    trade_count?: number;
    disclaimer?: string;
  };
};

function formatUptime(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  return `${h}h ${m}m`;
}

export default async function SystemHealthPage() {
  await requireUser();
  const [health, reports] = await Promise.all([
    soft(() => apiFetch<SystemHealth>("/api/v1/operations/system-health")),
    soft(() => apiFetch<DailyReport[]>("/api/v1/operations/daily-reports?limit=14")),
  ]);

  return (
    <>
      <PageHeader
        title="System Health"
        description="Operational observability for sustained paper trading. Live execution remains disabled. Metrics and reports reflect Internal Paper Provider activity only."
      />

      {!health ? (
        <ErrorState>
          System health unavailable. Confirm the API is reachable and migrations
          include Phase 15 operational tables.
        </ErrorState>
      ) : (
        <>
          <div className="grid grid-2">
            <Panel title="Overall status">
              <dl style={{ margin: 0, display: "grid", gap: "0.55rem" }}>
                <div>
                  <dt className="metric-label">Status</dt>
                  <dd style={{ margin: 0 }}>
                    <StatusBadge status={health.overall_status} label={health.overall_status} />
                  </dd>
                </div>
                <div>
                  <dt className="metric-label">Healthy / Warnings / Critical</dt>
                  <dd style={{ margin: 0 }}>
                    {health.healthy_service_count} / {health.warning_service_count} /{" "}
                    {health.critical_service_count}
                  </dd>
                </div>
                <div>
                  <dt className="metric-label">Process uptime</dt>
                  <dd style={{ margin: 0 }}>{formatUptime(health.uptime_seconds)}</dd>
                </div>
                <div>
                  <dt className="metric-label">Last restart</dt>
                  <dd style={{ margin: 0 }}>
                    {formatTimestamp(health.process_started_at)}
                  </dd>
                </div>
                <div>
                  <dt className="metric-label">Postgres / Redis</dt>
                  <dd style={{ margin: 0 }}>
                    {health.readiness?.postgres ? "ready" : "not ready"} /{" "}
                    {health.readiness?.redis ? "ready" : "not ready"}
                  </dd>
                </div>
                <div>
                  <dt className="metric-label">Generated</dt>
                  <dd style={{ margin: 0 }}>{formatTimestamp(health.generated_at)}</dd>
                </div>
              </dl>
            </Panel>

            <Panel title="Paper trading status">
              <dl style={{ margin: 0, display: "grid", gap: "0.55rem" }}>
                <div>
                  <dt className="metric-label">Default provider</dt>
                  <dd style={{ margin: 0 }}>
                    {health.paper.default_provider_key ?? "unavailable"}
                    {health.paper.default_provider_is_internal_paper
                      ? " (internal_paper)"
                      : ""}
                  </dd>
                </div>
                <div>
                  <dt className="metric-label">Active kill switches</dt>
                  <dd style={{ margin: 0 }}>{health.paper.active_kill_switch_count}</dd>
                </div>
                <div>
                  <dt className="metric-label">Last paper trade</dt>
                  <dd style={{ margin: 0 }}>
                    {health.paper.last_paper_order_at
                      ? formatTimestamp(health.paper.last_paper_order_at)
                      : "none yet"}
                  </dd>
                </div>
                <div>
                  <dt className="metric-label">Last reconciliation</dt>
                  <dd style={{ margin: 0 }}>
                    {health.reconciliation.available
                      ? `${health.reconciliation.status} @ ${formatTimestamp(health.reconciliation.started_at ?? "")}`
                      : health.reconciliation.note ?? "unavailable"}
                  </dd>
                </div>
                <div>
                  <dt className="metric-label">Last backup</dt>
                  <dd style={{ margin: 0 }}>
                    {health.backup?.available
                      ? `${formatTimestamp(health.backup.completed_at ?? null)} · integrity=${
                          health.backup.integrity_ok == null
                            ? "unknown"
                            : health.backup.integrity_ok
                              ? "ok"
                              : "failed"
                        }`
                      : health.backup?.note ?? "unavailable"}
                  </dd>
                </div>
              </dl>
            </Panel>
          </div>

          <div className="grid grid-2">
            <Panel title="Runtime monitor">
              {!health.runtime_monitor ? (
                <EmptyState>Runtime monitor unavailable.</EmptyState>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Component</th>
                      <th>Status</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(health.runtime_monitor).map(([key, probe]) => (
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
              )}
            </Panel>

            <Panel title="Active alerts">
              {!health.active_alerts || health.active_alerts.length === 0 ? (
                <EmptyState>No active critical/high alerts.</EmptyState>
              ) : (
                <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                  {health.active_alerts.map((a, idx) => (
                    <li key={`${a.kind}-${idx}`}>
                      [{a.severity}] {a.description}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <div className="grid grid-2">
            <Panel title="Host resources">
              {!health.host ? (
                <EmptyState>
                  No host snapshot yet. Capture via API or wait for the health
                  supervisor cron (every 5 minutes when the worker is running).
                </EmptyState>
              ) : (
                <dl style={{ margin: 0, display: "grid", gap: "0.55rem" }}>
                  <div>
                    <dt className="metric-label">CPU %</dt>
                    <dd style={{ margin: 0 }}>{health.host.cpu_percent.toFixed(1)}</dd>
                  </div>
                  <div>
                    <dt className="metric-label">Memory %</dt>
                    <dd style={{ margin: 0 }}>{health.host.memory_percent.toFixed(1)}</dd>
                  </div>
                  <div>
                    <dt className="metric-label">Disk %</dt>
                    <dd style={{ margin: 0 }}>{health.host.disk_percent.toFixed(1)}</dd>
                  </div>
                  <div>
                    <dt className="metric-label">Captured</dt>
                    <dd style={{ margin: 0 }}>
                      {formatTimestamp(health.host.captured_at)}
                    </dd>
                  </div>
                </dl>
              )}
            </Panel>

            <Panel title="Incidents by severity">
              <dl style={{ margin: 0, display: "grid", gap: "0.55rem" }}>
                {(["critical", "high", "medium", "info"] as const).map((sev) => (
                  <div key={sev}>
                    <dt className="metric-label">{sev}</dt>
                    <dd style={{ margin: 0 }}>
                      {health.incidents_by_severity?.[sev] ?? 0}
                    </dd>
                  </div>
                ))}
              </dl>
            </Panel>
          </div>

          <Panel title="Workers / queue proxies">
            {health.worker_instances.length === 0 ? (
              <EmptyState>
                No worker instances registered. Start the health supervisor worker
                profile when you need scheduled host metrics and daily reports.
              </EmptyState>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Instance</th>
                    <th>Status</th>
                    <th>Last seen</th>
                  </tr>
                </thead>
                <tbody>
                  {health.worker_instances.map((w) => (
                    <tr key={w.instance_key}>
                      <td>{w.instance_key}</td>
                      <td>
                        <StatusBadge status={w.status} label={w.status} />
                      </td>
                      <td>{formatTimestamp(w.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <p style={{ marginTop: "0.75rem", opacity: 0.8, fontSize: "0.9rem" }}>
              Queue health is reflected via Redis readiness and worker last-seen
              heartbeats — Argus does not run a separate broker product.
            </p>
          </Panel>

          <Panel title="Governed services">
            {health.services.length === 0 ? (
              <EmptyState>No registered services.</EmptyState>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Service</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {health.services.map((s) => (
                    <tr key={s.service_key}>
                      <td>{s.display_name}</td>
                      <td>
                        <StatusBadge status={s.status} label={s.status} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>

          <Panel title="Recent operational events">
            {health.recent_events.length === 0 ? (
              <EmptyState>No operational events recorded yet.</EmptyState>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Component</th>
                    <th>Severity</th>
                    <th>Description</th>
                    <th>Correlation</th>
                  </tr>
                </thead>
                <tbody>
                  {health.recent_events.map((e, idx) => (
                    <tr key={`${e.correlation_id}-${idx}`}>
                      <td>{formatTimestamp(e.occurred_at)}</td>
                      <td>{e.component}</td>
                      <td>{e.severity}</td>
                      <td>{e.description}</td>
                      <td style={{ fontFamily: "monospace", fontSize: "0.8rem" }}>
                        {e.correlation_id}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>

          <Panel title="Incident history">
            {!health.incident_history || health.incident_history.length === 0 ? (
              <EmptyState>No incidents recorded.</EmptyState>
            ) : (
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Severity</th>
                    <th>Status</th>
                    <th>Opened</th>
                  </tr>
                </thead>
                <tbody>
                  {health.incident_history.map((row) => (
                    <tr key={row.id}>
                      <td>{row.title}</td>
                      <td>{row.severity}</td>
                      <td>{row.status}</td>
                      <td>{formatTimestamp(row.opened_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Panel>
        </>
      )}

      <Panel title="Daily trading reports (paper)">
        <div style={{ marginBottom: "1rem" }}>
          <GenerateDailyReportForm />
        </div>
        {!reports ? (
          <ErrorState>Daily reports unavailable.</ErrorState>
        ) : reports.length === 0 ? (
          <EmptyState>
            No daily reports yet. Use Generate above, the Control Center shortcut, or
            wait for the 00:15 UTC worker cron.
          </EmptyState>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Trades</th>
                <th>Immutable</th>
                <th>Generated</th>
              </tr>
            </thead>
            <tbody>
              {reports.map((r) => (
                <tr key={r.id}>
                  <td>{r.report_date}</td>
                  <td>{r.content?.trade_count ?? "—"}</td>
                  <td>{r.is_immutable ? "yes" : "no"}</td>
                  <td>{formatTimestamp(r.generated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
    </>
  );
}
