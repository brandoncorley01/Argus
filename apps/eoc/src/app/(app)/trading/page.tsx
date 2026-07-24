import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState, PageHeader, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { direction, money, pnlClass } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";
import { apiFetch } from "@/lib/server/api";
import { soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Trading" };

type Portfolio = { id: string; name: string; kill_switch_active: boolean };
type Position = {
  symbol: string;
  quantity: string;
  average_cost: string;
  unrealized_pnl: string;
  realized_pnl: string;
};
type Order = {
  id: string;
  symbol: string;
  side: string;
  status: string;
  quantity: string;
  average_fill_price?: string | null;
  created_at: string;
};
type Fill = {
  symbol: string;
  side: string;
  quantity: string;
  price: string;
  filled_at: string;
};
type DailyReport = {
  content?: {
    daily_pnl?: string | null;
    trade_count?: number;
    win_rate?: string | null;
  };
};

export default async function TradingPage() {
  await requireUser();
  const [portfolios, reports] = await Promise.all([
    soft(() => apiFetch<Portfolio[]>("/api/v1/paper/portfolios")),
    soft(() =>
      apiFetch<DailyReport[]>("/api/v1/operations/daily-reports", {
        searchParams: { limit: 1 },
      }),
    ),
  ]);
  const portfolio = portfolios?.[0] ?? null;
  let positions: Position[] = [];
  let orders: Order[] = [];
  let fills: Fill[] = [];
  if (portfolio) {
    const [p, o, f] = await Promise.all([
      soft(() =>
        apiFetch<Position[]>(`/api/v1/paper/portfolios/${portfolio.id}/positions`),
      ),
      soft(() =>
        apiFetch<Order[]>(`/api/v1/paper/portfolios/${portfolio.id}/orders`),
      ),
      soft(() =>
        apiFetch<Fill[]>(`/api/v1/paper/portfolios/${portfolio.id}/fills`),
      ),
    ]);
    positions = p ?? [];
    orders = o ?? [];
    fills = f ?? [];
  }

  const open = positions.filter((x) => Number(x.quantity) !== 0);
  const unrealized = open.reduce((s, x) => s + (Number(x.unrealized_pnl) || 0), 0);
  const realizedToday = reports?.[0]?.content?.daily_pnl ?? null;
  const closedish = fills.slice(0, 8);

  return (
    <>
      <PageHeader
        title="Trading"
        description="Simple daily review. Technical IDs stay in Advanced → Paper details."
      />

      <div className="simple-row">
        <div className="simple-chip">
          <span className="metric-label">Status</span>
          <strong>{portfolio?.kill_switch_active ? "Paused" : "Active"}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Realized P&amp;L</span>
          <strong className={pnlClass(realizedToday)}>{money(realizedToday)}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Unrealized P&amp;L</span>
          <strong className={pnlClass(unrealized)}>{money(unrealized)}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Trades (report)</span>
          <strong>{reports?.[0]?.content?.trade_count ?? "Unavailable"}</strong>
        </div>
      </div>

      <div className="grid grid-2" style={{ marginTop: "1rem" }}>
        <Panel title="Open positions">
          {open.length === 0 ? (
            <EmptyState>No open positions.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Entry</th>
                    <th>Unrealized</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {open.map((p) => (
                    <tr key={p.symbol}>
                      <td>{p.symbol}</td>
                      <td>{direction(p.quantity)}</td>
                      <td>{money(p.average_cost)}</td>
                      <td className={pnlClass(p.unrealized_pnl)}>
                        {money(p.unrealized_pnl)}
                      </td>
                      <td>Open</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted-note">
            Stop / target / live mark price are not provided by paper books yet —
            shown as Unavailable when missing.
          </p>
        </Panel>

        <Panel title="Recent fills">
          {closedish.length === 0 ? (
            <EmptyState>No recent fills.</EmptyState>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>When</th>
                  </tr>
                </thead>
                <tbody>
                  {closedish.map((f, i) => (
                    <tr key={`${f.symbol}-${f.filled_at}-${i}`}>
                      <td>{f.symbol}</td>
                      <td>{f.side === "buy" ? "Buy" : "Sell"}</td>
                      <td>{f.quantity}</td>
                      <td>{money(f.price)}</td>
                      <td>{formatTimestamp(f.filled_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>

      <details className="tech-details">
        <summary>Technical order list (optional)</summary>
        {orders.length === 0 ? (
          <EmptyState>No orders.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Status</th>
                  <th>Qty</th>
                  <th>Avg fill</th>
                </tr>
              </thead>
              <tbody>
                {orders.slice(0, 20).map((o) => (
                  <tr key={o.id}>
                    <td>{o.symbol}</td>
                    <td>{o.side}</td>
                    <td>{o.status}</td>
                    <td>{o.quantity}</td>
                    <td>{o.average_fill_price ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </details>

      <div className="form-actions" style={{ marginTop: "1rem" }}>
        <Link className="btn secondary" href="/today">
          Home
        </Link>
        <Link className="btn secondary" href="/paper">
          Advanced paper details
        </Link>
      </div>
    </>
  );
}
