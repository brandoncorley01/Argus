import type { Metadata } from "next";
import Link from "next/link";

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

export const metadata: Metadata = { title: "Paper Trading" };

type ProviderRow = {
  provider: {
    provider_key: string;
    display_name: string;
    environment: string;
    is_default: boolean;
  };
  health: { status: string } | null;
};

type Portfolio = {
  id: string;
  name: string;
  cash_balance: string;
  status: string;
  kill_switch_active: boolean;
  created_at: string;
};

export default async function PaperPage() {
  await requireUser();
  const [providers, portfolios] = await Promise.all([
    soft(() => apiFetch<ProviderRow[]>("/api/v1/paper/providers")),
    soft(() => apiFetch<Portfolio[]>("/api/v1/paper/portfolios")),
  ]);

  return (
    <>
      <PageHeader
        title="Paper Trading Institution"
        description="Internal paper execution only. No brokerage account, exchange credentials, or real capital. Empty books mean no paper activity yet."
      />
      <div className="grid grid-2">
        <Panel title="Execution providers">
          {!providers ? (
            <ErrorState>Providers unavailable.</ErrorState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th>Environment</th>
                    <th>Default</th>
                    <th>Health</th>
                  </tr>
                </thead>
                <tbody>
                  {providers.map((r) => (
                    <tr key={r.provider.provider_key}>
                      <td>{r.provider.display_name}</td>
                      <td>{r.provider.environment}</td>
                      <td>{r.provider.is_default ? "yes" : "no"}</td>
                      <td>
                        <StatusBadge
                          status={r.health?.status}
                          label={r.health?.status ?? "unknown"}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        <Panel title="Paper portfolios">
          {!portfolios ? (
            <ErrorState>Portfolios unavailable.</ErrorState>
          ) : portfolios.length === 0 ? (
            <EmptyState>No paper portfolios.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Cash</th>
                    <th>Status</th>
                    <th>Kill switch</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {portfolios.map((p) => (
                    <tr key={p.id}>
                      <td>{p.name}</td>
                      <td>{p.cash_balance}</td>
                      <td>{p.status}</td>
                      <td>{p.kill_switch_active ? "ACTIVE" : "off"}</td>
                      <td>
                        <Link href={`/paper/${p.id}`}>Open</Link>
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
