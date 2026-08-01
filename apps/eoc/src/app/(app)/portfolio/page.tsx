import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState, PageHeader, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { pickPrimaryPortfolio } from "@/lib/founder/learningDesk";
import { money, pnlClass } from "@/lib/founder/simple";
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

type PortfolioSummary = {
  cash_balance: string;
  buying_power: string;
  committed_capital: string;
  total_account_value: string;
  open_position_count: number;
};

type PositionSummary = {
  symbol: string;
  quantity: string;
  side: string;
  average_cost: string;
  committed_capital: string;
  unrealized_pnl: string | null;
  realized_pnl: string;
  mark_price: string | null;
  market_value?: string | null;
};

export default async function PortfolioPage() {
  await requireUser();
  const portfolios = await soft(() => apiFetch<Portfolio[]>("/api/v1/paper/portfolios"));
  const portfolio = pickPrimaryPortfolio(portfolios) ?? null;
  let summary: PortfolioSummary | null = null;
  let positions: PositionSummary[] = [];
  if (portfolio) {
    const [s, p] = await Promise.all([
      soft(() =>
        apiFetch<PortfolioSummary>(
          `/api/v1/paper/portfolios/${portfolio.id}/summary`,
        ),
      ),
      soft(() =>
        apiFetch<PositionSummary[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/position-summaries`,
        ),
      ),
    ]);
    summary = s;
    positions = p ?? [];
  }
  const open = positions.filter((p) => Number(p.quantity) !== 0);
  const deployed = summary
    ? Number(summary.committed_capital)
    : open.reduce((s, p) => s + (Number(p.committed_capital) || 0), 0);
  const unrealized = open.reduce((s, p) => {
    const n = Number(p.unrealized_pnl);
    return s + (Number.isFinite(n) ? n : 0);
  }, 0);
  const value = summary ? Number(summary.total_account_value) : null;
  const cash = summary?.cash_balance ?? portfolio?.cash_balance ?? null;

  const bySymbol = open.map((p) => ({
    symbol: p.symbol,
    exposure: Number(p.committed_capital) || 0,
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
              <strong title="Cash + open marks (same as Home)">
                {value == null || !Number.isFinite(value) ? "Unavailable" : money(value)}
              </strong>
            </div>
            <div className="simple-chip">
              <span className="metric-label">Paper cash</span>
              <strong>{cash == null ? "Unavailable" : money(cash)}</strong>
            </div>
            <div className="simple-chip">
              <span className="metric-label">Capital deployed</span>
              <strong title="Open position cost basis">{money(deployed)}</strong>
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
                        <th>Mark</th>
                        <th>Unrealized</th>
                      </tr>
                    </thead>
                    <tbody>
                      {open.map((p) => (
                        <tr key={p.symbol}>
                          <td>
                            <Link href={`/paper/${portfolio.id}`}>{p.symbol}</Link>
                          </td>
                          <td>{p.side === "short" ? "Short" : "Long"}</td>
                          <td>{p.quantity}</td>
                          <td>{p.mark_price != null ? money(p.mark_price) : "—"}</td>
                          <td className={pnlClass(Number(p.unrealized_pnl) || 0)}>
                            {p.unrealized_pnl != null ? money(p.unrealized_pnl) : "—"}
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
    </>
  );
}
