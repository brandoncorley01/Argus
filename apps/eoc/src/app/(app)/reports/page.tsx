import type { Metadata } from "next";
import Link from "next/link";

import { EndDayButton } from "@/components/founder/EndDayButton";
import { GenerateDailyReportForm } from "@/components/GenerateDailyReportForm";
import { EmptyState, PageHeader, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { money, pnlClass } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";
import { isFounder, isOperator } from "@/lib/rbac";
import { apiFetch } from "@/lib/server/api";
import { soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Reports" };

type DailyReport = {
  id: string;
  report_date: string;
  generated_at: string;
  is_immutable: boolean;
  content?: {
    daily_pnl?: string | null;
    trade_count?: number;
    disclaimer?: string;
  };
};

export default async function ReportsPage() {
  const user = await requireUser();
  const canGenerate = isFounder(user) || isOperator(user);
  const reports = await soft(() =>
    apiFetch<DailyReport[]>("/api/v1/operations/daily-reports", {
      searchParams: { limit: 14 },
    }),
  );
  const latest = reports?.[0] ?? null;

  return (
    <>
      <PageHeader
        title="Reports"
        description="Daily paper summaries. Live trading stays locked."
      />

      <Panel title="Latest report">
        {!latest ? (
          <EmptyState>No daily report yet.</EmptyState>
        ) : (
          <dl className="summary-dl">
            <div>
              <dt>Date</dt>
              <dd>{latest.report_date}</dd>
            </div>
            <div>
              <dt>P&amp;L</dt>
              <dd className={pnlClass(latest.content?.daily_pnl ?? null)}>
                {money(latest.content?.daily_pnl)}
              </dd>
            </div>
            <div>
              <dt>Trades</dt>
              <dd>{latest.content?.trade_count ?? "Unavailable"}</dd>
            </div>
            <div>
              <dt>Generated</dt>
              <dd>{formatTimestamp(latest.generated_at)}</dd>
            </div>
          </dl>
        )}
      </Panel>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Generate report">
          {canGenerate ? (
            <>
              <p className="muted-note">
                If a report already exists for the date, Argus keeps it and tells you
                plainly — no technical conflict wording.
              </p>
              <GenerateDailyReportForm />
            </>
          ) : (
            <EmptyState>Founder or Operator required to generate reports.</EmptyState>
          )}
        </Panel>
        <Panel title="End Trading Day">
          <p className="muted-note">
            Report + backup in one step. Positions stay open. Argus keeps running until
            you Stop.
          </p>
          <EndDayButton />
        </Panel>
      </div>

      <Panel title="Recent daily reports" className="rise-delay-2">
        {!reports || reports.length === 0 ? (
          <EmptyState>No history yet.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>P&amp;L</th>
                  <th>Trades</th>
                  <th>Generated</th>
                </tr>
              </thead>
              <tbody>
                {reports.map((r) => (
                  <tr key={r.id}>
                    <td>{r.report_date}</td>
                    <td className={pnlClass(r.content?.daily_pnl ?? null)}>
                      {money(r.content?.daily_pnl)}
                    </td>
                    <td>{r.content?.trade_count ?? "—"}</td>
                    <td>{formatTimestamp(r.generated_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <div className="form-actions" style={{ marginTop: "1rem" }}>
        <Link className="btn secondary" href="/today">
          Home
        </Link>
        <Link className="btn secondary" href="/system-health">
          Advanced report tools
        </Link>
      </div>
    </>
  );
}
