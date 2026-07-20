import type { Metadata } from "next";

import {
  AllocationActions,
  AllocationRequestForm,
  AttributionGenerateForm,
  ExternalTransferActions,
  ExternalTransferCreateForm,
  ForecastForm,
  KpiGenerateButton,
  ReportGenerateForm,
} from "@/components/TreasuryForms";
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
import { isFounder, isOperator } from "@/lib/rbac";
import {
  getAttributionSnapshots,
  getCapitalAllocations,
  getCapitalPools,
  getExecutiveKpis,
  getExternalTransfers,
  getForecastScenarios,
  getInstitutionalReports,
  getTreasuryAccounts,
  getTreasurySummary,
  soft,
} from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Treasury & Executive Analytics" };

export default async function TreasuryPage() {
  const user = await requireUser();
  const [
    summary,
    accounts,
    pools,
    allocations,
    transfers,
    attribution,
    kpis,
    forecasts,
    reports,
  ] = await Promise.all([
    soft(getTreasurySummary),
    soft(getTreasuryAccounts),
    soft(getCapitalPools),
    soft(getCapitalAllocations),
    soft(getExternalTransfers),
    soft(getAttributionSnapshots),
    soft(getExecutiveKpis),
    soft(getForecastScenarios),
    soft(getInstitutionalReports),
  ]);

  return (
    <>
      <PageHeader
        title="Treasury & Executive Analytics"
        description="Every balance, allocation, and KPI below represents SIMULATED / INTERNAL PAPER capital only. No real deposit, withdrawal, or external transfer can ever be executed from this system."
      />

      <div className="state-block" style={{ marginBottom: "1.5rem" }}>
        {summary?.disclaimer ??
          "All figures on this page are simulated paper capital. No real money is held or movable."}
      </div>

      {!summary ? (
        <ErrorState>Treasury summary unavailable.</ErrorState>
      ) : (
        <div className="grid grid-4" style={{ marginBottom: "1rem" }}>
          <Metric
            label="Total simulated balance"
            value={summary.total_simulated_balance}
            hint={`${summary.account_count} account(s)`}
          />
          <Metric
            label="External transfers executed"
            value={summary.external_transfer_executed_count}
            hint="Always zero — execution is forbidden"
          />
          <Metric
            label="Live performance available"
            value={summary.live_available ? "yes" : "no"}
            hint={summary.live_unavailable_reason}
          />
          <Metric
            label="Latest report version"
            value={summary.latest_report ? `v${summary.latest_report.version}` : "—"}
            hint={summary.latest_report?.report_type ?? "none generated"}
          />
        </div>
      )}

      <div className="grid grid-2">
        <Panel title="Treasury accounts (simulated only)">
          {!accounts ? (
            <ErrorState>Accounts unavailable.</ErrorState>
          ) : accounts.length === 0 ? (
            <EmptyState>No treasury accounts.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Classification</th>
                    <th>Balance</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {accounts.map((a) => (
                    <tr key={a.id}>
                      <td>{a.name}</td>
                      <td>{a.classification}</td>
                      <td>{a.balance}</td>
                      <td>
                        <StatusBadge
                          status={a.status === "active" ? "healthy" : "degraded"}
                          label={a.status}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Capital pools">
          {!pools ? (
            <ErrorState>Pools unavailable.</ErrorState>
          ) : pools.length === 0 ? (
            <EmptyState>No capital pools.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Balance</th>
                  </tr>
                </thead>
                <tbody>
                  {pools.map((p) => (
                    <tr key={p.id}>
                      <td>{p.name}</td>
                      <td>{p.pool_type}</td>
                      <td>{p.balance}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="Capital allocations">
          {!allocations ? (
            <ErrorState>Allocations unavailable.</ErrorState>
          ) : allocations.length === 0 ? (
            <EmptyState>No capital allocations yet.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Target</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Requested</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {allocations.map((a) => (
                    <tr key={a.id}>
                      <td>
                        {a.target_type}
                        {a.target_id ? ` · ${a.target_id}` : ""}
                      </td>
                      <td>{a.amount}</td>
                      <td>
                        <StatusBadge
                          status={
                            a.status === "active"
                              ? "healthy"
                              : a.status === "rejected"
                                ? "unhealthy"
                                : "degraded"
                          }
                          label={a.status}
                        />
                      </td>
                      <td>{formatTimestamp(a.requested_at)}</td>
                      <td>
                        <AllocationActions
                          allocationId={a.id}
                          status={a.status}
                          canApprove={isFounder(user)}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {isFounder(user) ? (
            <div style={{ marginTop: "1rem" }}>
              <AllocationRequestForm pools={pools ?? []} />
            </div>
          ) : (
            <EmptyState>Founder role required to request allocations.</EmptyState>
          )}
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="External transfer instructions — draft/proposed/cancelled only, never executed">
          {!transfers ? (
            <ErrorState>External transfers unavailable.</ErrorState>
          ) : transfers.length === 0 ? (
            <EmptyState>No external transfer instructions.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Direction</th>
                    <th>Amount</th>
                    <th>Destination</th>
                    <th>Status</th>
                    <th>Blocked reason</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {transfers.map((t) => (
                    <tr key={t.id}>
                      <td>{t.direction}</td>
                      <td>
                        {t.amount} {t.currency}
                      </td>
                      <td>{t.destination_reference}</td>
                      <td>
                        <StatusBadge
                          status={t.status === "cancelled" ? "unhealthy" : "degraded"}
                          label={t.status}
                        />
                      </td>
                      <td>{t.blocked_reason ?? "—"}</td>
                      <td>
                        {isFounder(user) ? (
                          <ExternalTransferActions instructionId={t.id} status={t.status} />
                        ) : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {isFounder(user) ? (
            <div style={{ marginTop: "1rem" }}>
              <ExternalTransferCreateForm accounts={accounts ?? []} />
            </div>
          ) : (
            <EmptyState>Founder role required to create transfer instructions.</EmptyState>
          )}
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Performance attribution (PAPER labeled — live always unavailable)">
          {!attribution ? (
            <ErrorState>Attribution unavailable.</ErrorState>
          ) : attribution.length === 0 ? (
            <EmptyState>No attribution snapshots generated yet.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Scope</th>
                    <th>Environment</th>
                    <th>Available</th>
                    <th>As of</th>
                  </tr>
                </thead>
                <tbody>
                  {attribution.map((s) => (
                    <tr key={s.id}>
                      <td>
                        {s.scope}
                        {s.scope_ref ? ` · ${s.scope_ref}` : ""}
                      </td>
                      <td>
                        <StatusBadge
                          status={s.environment_class === "live" ? "unhealthy" : "healthy"}
                          label={s.environment_class}
                        />
                      </td>
                      <td>{s.is_available ? "yes" : `no — ${s.unavailable_reason ?? "unavailable"}`}</td>
                      <td>{formatTimestamp(s.as_of)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {isOperator(user) ? (
            <div style={{ marginTop: "1rem" }}>
              <AttributionGenerateForm />
            </div>
          ) : (
            <EmptyState>Operator or Founder role required to generate attribution.</EmptyState>
          )}
        </Panel>

        <Panel title="Executive KPIs (evidence-backed)">
          {!kpis ? (
            <ErrorState>KPIs unavailable.</ErrorState>
          ) : kpis.length === 0 ? (
            <EmptyState>No KPI snapshots generated yet.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Value</th>
                    <th>Environment</th>
                    <th>Estimated</th>
                  </tr>
                </thead>
                <tbody>
                  {kpis.slice(0, 15).map((k) => (
                    <tr key={k.id}>
                      <td>{k.kpi_key}</td>
                      <td>
                        {k.value ?? "—"} {k.unit}
                      </td>
                      <td>{k.environment_class}</td>
                      <td>{k.is_estimated ? "yes" : "no"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {isOperator(user) ? (
            <div style={{ marginTop: "1rem" }}>
              <KpiGenerateButton />
            </div>
          ) : (
            <EmptyState>Operator or Founder role required to generate KPIs.</EmptyState>
          )}
        </Panel>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Forecast scenarios (deterministic, no market predictions)">
          {!forecasts ? (
            <ErrorState>Forecasts unavailable.</ErrorState>
          ) : forecasts.length === 0 ? (
            <EmptyState>No forecast scenarios generated yet.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>As of</th>
                  </tr>
                </thead>
                <tbody>
                  {forecasts.map((f) => (
                    <tr key={f.id}>
                      <td>{f.name}</td>
                      <td>{f.scenario_type}</td>
                      <td>{formatTimestamp(f.as_of)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {isOperator(user) ? (
            <div style={{ marginTop: "1rem" }}>
              <ForecastForm />
            </div>
          ) : (
            <EmptyState>Operator or Founder role required to generate forecasts.</EmptyState>
          )}
        </Panel>

        <Panel title="Institutional reports (immutable, hashed, paper vs. live labeled)">
          {!reports ? (
            <ErrorState>Reports unavailable.</ErrorState>
          ) : reports.length === 0 ? (
            <EmptyState>No institutional reports generated yet.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Type</th>
                    <th>Version</th>
                    <th>Hash</th>
                    <th>As of</th>
                  </tr>
                </thead>
                <tbody>
                  {reports.map((r) => (
                    <tr key={r.id}>
                      <td>{r.report_type}</td>
                      <td>{r.version}</td>
                      <td style={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
                        {r.content_hash.slice(0, 12)}…
                      </td>
                      <td>{formatTimestamp(r.as_of)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {isOperator(user) ? (
            <div style={{ marginTop: "1rem" }}>
              <ReportGenerateForm />
            </div>
          ) : (
            <EmptyState>Operator or Founder role required to generate reports.</EmptyState>
          )}
        </Panel>
      </div>
    </>
  );
}
