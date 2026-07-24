import type { Metadata } from "next";
import Link from "next/link";

import {
  EmptyState,
  ErrorState,
  PageHeader,
  Panel,
} from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { formatTimestamp } from "@/lib/format";
import { apiFetch } from "@/lib/server/api";
import { soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Strategy Laboratory" };

type StrategyDoc = {
  id: string;
  strategy_key: string;
  name: string;
  status: string;
  updated_at: string;
};

type ResearchRun = {
  id: string;
  kind: string;
  status: string;
  strategy_version_id: string;
  created_at: string;
  finished_at: string | null;
};

type Dataset = {
  id: string;
  dataset_key: string;
  name: string;
  provenance: string;
  source_kind: string;
  bar_count: number;
};

async function listStrategies() {
  return apiFetch<StrategyDoc[]>("/api/v1/strategies");
}
async function listRuns() {
  return apiFetch<ResearchRun[]>("/api/v1/strategies/runs", {
    searchParams: { limit: 30 },
  });
}
async function listDatasets() {
  return apiFetch<Dataset[]>("/api/v1/strategies/datasets");
}

export default async function StrategiesPage() {
  await requireUser();
  const [docs, runs, datasets] = await Promise.all([
    soft(listStrategies),
    soft(listRuns),
    soft(listDatasets),
  ]);

  return (
    <>
      <PageHeader
        title="Strategy Laboratory"
        description="Governed quantitative research. Strategies are institutional assets — versioned, reviewed, and tested without live capital. Metrics shown are research evidence only, not claims of live profitability."
      />

      <div className="grid grid-2" style={{ marginBottom: "1rem" }}>
        <Panel title="Strategy registry">
          {!docs ? (
            <ErrorState>Strategy API unavailable.</ErrorState>
          ) : docs.length === 0 ? (
            <EmptyState>No strategies registered.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Name</th>
                    <th>Status</th>
                    <th>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {docs.map((d) => (
                    <tr key={d.id}>
                      <td>
                        <Link href={`/strategies/${d.id}`}>{d.strategy_key}</Link>
                      </td>
                      <td>{d.name}</td>
                      <td>{d.status}</td>
                      <td>{formatTimestamp(d.updated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>

        <Panel title="Research datasets">
          {!datasets ? (
            <ErrorState>Datasets unavailable.</ErrorState>
          ) : datasets.length === 0 ? (
            <EmptyState>No research datasets. Register fixtures with provenance.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Source</th>
                    <th>Bars</th>
                    <th>Provenance</th>
                  </tr>
                </thead>
                <tbody>
                  {datasets.map((ds) => (
                    <tr key={ds.id}>
                      <td>{ds.dataset_key}</td>
                      <td>{ds.source_kind}</td>
                      <td>{ds.bar_count}</td>
                      <td style={{ fontSize: "0.85rem" }}>{ds.provenance}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <Panel title="Research runs">
        {!runs ? (
          <ErrorState>Runs unavailable.</ErrorState>
        ) : runs.length === 0 ? (
          <EmptyState>No research runs yet.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Kind</th>
                  <th>Status</th>
                  <th>Version</th>
                  <th>Created</th>
                  <th>Finished</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.id}>
                    <td>{r.kind}</td>
                    <td>{r.status}</td>
                    <td style={{ fontSize: "0.8rem" }}>{r.strategy_version_id}</td>
                    <td>{formatTimestamp(r.created_at)}</td>
                    <td>{formatTimestamp(r.finished_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
