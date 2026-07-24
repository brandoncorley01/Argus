import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState, PageHeader, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { direction, money, pnlClass } from "@/lib/founder/simple";
import { apiFetch } from "@/lib/server/api";
import { soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Portfolio" };

type Portfolio = {
  id: string;
  name: string;
  cash_balance: string;
  reserved_cash: string;
  status: string;
  kill_switch_active: boolean;
};
type Position = {
  symbol: string;
  quantity: string;
  average_cost: string;
  unrealized_pnl: string;
  realized_pnl: string;
};

export default async function PortfolioPage() {
  await requireUser();
  const portfolios = await soft(() => apiFetch<Portfolio[]>("/api/v1/paper/portfolios"));
  const portfolio = portfolios?.[0] ?? null;
  let positions: Position[] = [];
  if (portfolio) {
    positions =
      (await soft(() =>
        apiFetch<Position[]>(`/api/v1/paper/portfolios/${portfolio.id}/positions`),
      )) ?? [];
  }
  const open = positions.filter((p) => Number(p.quantity) !== 0);
  const deployed = open.reduce(
    (s, p) => s + Math.abs(Number(p.quantity) || 0) * (Number(p.average_cost) || 0),
    0,
  );
  const unrealized = open.reduce((s, p) => s + (Number(p.unrealized_pnl) || 0), 0);
  const realized = positions.reduce((s, p) => s + (Number(p.realized_pnl) || 0), 0);
  const cash = portfolio ? Number(portfolio.cash_balance) : NaN;
  const value =
    Number.isFinite(cash) && Number.isFinite(deployed) ? cash + deployed + unrealized : null;

  const bySymbol = open.map((p) => ({
    symbol: p.symbol,
    exposure: Math.abs(Number(p.quantity) || 0) * (Number(p.average_cost) || 0),
  }));

  return (
    <>
      <PageHeader
        title="Portfolio"
        description={portfolio ? portfolio.name : "Paper portfolio summary"}
      />

      {!portfolio ? (
        <EmptyState>No paper portfolio yet. Create one under Advanced → Paper details.</EmptyState>
      ) : (
        <>
          <div className="simple-row">
            <div className="simple-chip">
              <span className="metric-label">Portfolio value</span>
              <strong>{value == null ? "Unavailable" : money(value)}</strong>
            </div>
            <div className="simple-chip">
              <span className="metric-label">Paper cash</span>
              <strong>{money(portfolio.cash_balance)}</strong>
            </div>
            <div className="simple-chip">
              <span className="metric-label">Capital deployed</span>
              <strong title="Open position cost basis">{money(deployed)}</strong>
            </div>
            <div className="simple-chip">
              <span className="metric-label">Realized P&amp;L</span>
              <strong className={pnlClass(realized)} title="Closed gains/losses on books">
                {money(realized)}
              </strong>
            </div>
            <div className="simple-chip">
              <span className="metric-label">Unrealized P&amp;L</span>
              <strong className={pnlClass(unrealized)} title="Open position mark vs cost">
                {money(unrealized)}
              </strong>
            </div>
          </div>

          <div className="grid grid-2" style={{ marginTop: "1rem" }}>
            <Panel title="Exposure by asset">
              {bySymbol.length === 0 ? (
                <EmptyState>No open exposure.</EmptyState>
              ) : (
                <ul className="plain-list">
                  {bySymbol.map((row) => (
                    <li key={row.symbol}>
                      {row.symbol}: {money(row.exposure)}
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
            <Panel title="Open positions">
              {open.length === 0 ? (
                <EmptyState>Flat.</EmptyState>
              ) : (
                <div className="table-wrap">
                  <table className="data">
                    <thead>
                      <tr>
                        <th>Symbol</th>
                        <th>Side</th>
                        <th>Qty</th>
                        <th>Unrealized</th>
                      </tr>
                    </thead>
                    <tbody>
                      {open.map((p) => (
                        <tr key={p.symbol}>
                          <td>{p.symbol}</td>
                          <td>{direction(p.quantity)}</td>
                          <td>{p.quantity}</td>
                          <td className={pnlClass(p.unrealized_pnl)}>
                            {money(p.unrealized_pnl)}
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
      )}

      <div className="form-actions" style={{ marginTop: "1rem" }}>
        <Link className="btn secondary" href="/today">
          Home
        </Link>
        <Link className="btn secondary" href="/trading">
          Trading
        </Link>
      </div>
    </>
  );
}
