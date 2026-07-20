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

export const metadata: Metadata = { title: "Paper Portfolio" };

export default async function PaperPortfolioPage({ params }: Props) {
  await requireUser();
  const { id } = await params;
  const portfolio = await soft(() =>
    apiFetch<{
      id: string;
      name: string;
      cash_balance: string;
      reserved_cash: string;
      status: string;
      kill_switch_active: boolean;
    }>(`/api/v1/paper/portfolios/${id}`),
  );
  if (!portfolio) notFound();

  const [orders, fills, positions] = await Promise.all([
    soft(() =>
      apiFetch<
        Array<{
          id: string;
          symbol: string;
          side: string;
          status: string;
          quantity: string;
          filled_quantity: string;
          environment: string;
          created_at: string;
        }>
      >(`/api/v1/paper/portfolios/${id}/orders`),
    ),
    soft(() =>
      apiFetch<
        Array<{
          id: string;
          symbol: string;
          quantity: string;
          price: string;
          fee: string;
          filled_at: string;
        }>
      >(`/api/v1/paper/portfolios/${id}/fills`),
    ),
    soft(() =>
      apiFetch<
        Array<{
          id: string;
          symbol: string;
          quantity: string;
          average_cost: string;
          realized_pnl: string;
        }>
      >(`/api/v1/paper/portfolios/${id}/positions`),
    ),
  ]);

  return (
    <>
      <PageHeader
        title={portfolio.name}
        description={`Paper cash ${portfolio.cash_balance} · status ${portfolio.status}${portfolio.kill_switch_active ? " · KILL SWITCH" : ""}`}
        actions={
          <Link className="btn secondary" href="/paper">
            Back
          </Link>
        }
      />
      <div className="grid grid-3">
        <Panel title="Positions">
          {!positions ? (
            <ErrorState>Unavailable</ErrorState>
          ) : positions.length === 0 ? (
            <EmptyState>No positions.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Avg cost</th>
                    <th>Realized</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((p) => (
                    <tr key={p.id}>
                      <td>{p.symbol}</td>
                      <td>{p.quantity}</td>
                      <td>{p.average_cost}</td>
                      <td>{p.realized_pnl}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        <Panel title="Orders">
          {!orders ? (
            <ErrorState>Unavailable</ErrorState>
          ) : orders.length === 0 ? (
            <EmptyState>No orders.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Status</th>
                    <th>Env</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((o) => (
                    <tr key={o.id}>
                      <td>{o.symbol}</td>
                      <td>{o.side}</td>
                      <td>{o.status}</td>
                      <td>{o.environment}</td>
                      <td>{formatTimestamp(o.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
        <Panel title="Fills">
          {!fills ? (
            <ErrorState>Unavailable</ErrorState>
          ) : fills.length === 0 ? (
            <EmptyState>No fills.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Fee</th>
                  </tr>
                </thead>
                <tbody>
                  {fills.map((f) => (
                    <tr key={f.id}>
                      <td>{f.symbol}</td>
                      <td>{f.quantity}</td>
                      <td>{f.price}</td>
                      <td>{f.fee}</td>
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
