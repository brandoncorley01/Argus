import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

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

type Props = { params: Promise<{ id: string }> };

type StrategyDoc = {
  id: string;
  strategy_key: string;
  name: string;
  description: string | null;
  status: string;
};

type StrategyVersion = {
  id: string;
  version_number: number;
  version_label: string;
  status: string;
  strategy_class: string;
  is_immutable: boolean;
  content_hash: string;
  created_at: string;
  approved_at: string | null;
};

type ResearchRun = {
  id: string;
  kind: string;
  status: string;
  strategy_version_id: string;
  dataset_id: string;
  seed: number;
  request_hash: string;
  created_at: string;
  finished_at: string | null;
};

type ResearchResult = {
  id: string;
  run_id: string;
  metrics: Record<string, number>;
  in_sample_metrics: Record<string, number>;
  out_of_sample_metrics: Record<string, number>;
  result_hash: string;
  is_immutable: boolean;
};

export const metadata: Metadata = { title: "Strategy" };

export default async function StrategyDetailPage({ params }: Props) {
  await requireUser();
  const { id } = await params;
  const docs = await soft(() =>
    apiFetch<StrategyDoc[]>("/api/v1/strategies"),
  );
  const doc = docs?.find((d) => d.id === id);
  if (!doc) notFound();

  const versions = await soft(() =>
    apiFetch<StrategyVersion[]>(`/api/v1/strategies/${id}/versions`),
  );
  const versionIds = new Set((versions ?? []).map((v) => v.id));

  const allRuns = await soft(() =>
    apiFetch<ResearchRun[]>("/api/v1/strategies/runs", {
      searchParams: { limit: 50 },
    }),
  );
  const runs = (allRuns ?? []).filter((r) =>
    versionIds.has(r.strategy_version_id),
  );

  const resultPairs: Array<{ run: ResearchRun; result: ResearchResult | null }> =
    [];
  for (const run of runs.slice(0, 10)) {
    const results = await soft(() =>
      apiFetch<ResearchResult[]>(`/api/v1/strategies/runs/${run.id}/results`),
    );
    resultPairs.push({ run, result: results?.[0] ?? null });
  }

  return (
    <>
      <PageHeader
        title={doc.name}
        description={
          doc.description ??
          `${doc.strategy_key} — research evidence from the control plane only.`
        }
        actions={
          <Link className="btn secondary" href="/strategies">
            Back
          </Link>
        }
      />
      <Panel title="Document">
        <dl style={{ margin: 0, display: "grid", gap: "0.4rem" }}>
          <div>
            <dt className="metric-label">Key</dt>
            <dd style={{ margin: 0 }}>{doc.strategy_key}</dd>
          </div>
          <div>
            <dt className="metric-label">Status</dt>
            <dd style={{ margin: 0 }}>{doc.status}</dd>
          </div>
        </dl>
      </Panel>
      <div style={{ marginTop: "1rem" }}>
        <Panel title="Versions">
          {!versions ? (
            <ErrorState>Versions unavailable.</ErrorState>
          ) : versions.length === 0 ? (
            <EmptyState>No versions.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Label</th>
                    <th>Class</th>
                    <th>Status</th>
                    <th>Immutable</th>
                    <th>Hash</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {versions.map((v) => (
                    <tr key={v.id}>
                      <td>
                        {v.version_label} (#{v.version_number})
                      </td>
                      <td>{v.strategy_class}</td>
                      <td>{v.status}</td>
                      <td>{v.is_immutable ? "yes" : "no"}</td>
                      <td style={{ fontSize: "0.75rem" }}>{v.content_hash}</td>
                      <td>{formatTimestamp(v.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <div style={{ marginTop: "1rem" }}>
        <Panel title="Research evidence (runs + metrics)">
          {resultPairs.length === 0 ? (
            <EmptyState>
              No research runs for this strategy&apos;s versions yet. Empty means
              no evidence—not fabricated performance.
            </EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Kind</th>
                    <th>Status</th>
                    <th>Primary metrics</th>
                    <th>IS / OOS</th>
                    <th>Result hash</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {resultPairs.map(({ run, result }) => (
                    <tr key={run.id}>
                      <td>{run.kind}</td>
                      <td>{run.status}</td>
                      <td style={{ fontSize: "0.8rem" }}>
                        {result
                          ? JSON.stringify(result.metrics)
                          : "—"}
                      </td>
                      <td style={{ fontSize: "0.75rem" }}>
                        {result &&
                        (Object.keys(result.in_sample_metrics || {}).length > 0 ||
                          Object.keys(result.out_of_sample_metrics || {})
                            .length > 0)
                          ? `IS:${JSON.stringify(result.in_sample_metrics)} OOS:${JSON.stringify(result.out_of_sample_metrics)}`
                          : "—"}
                      </td>
                      <td style={{ fontSize: "0.7rem" }}>
                        {result?.result_hash ?? "—"}
                      </td>
                      <td>{formatTimestamp(run.created_at)}</td>
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
