import type { Metadata } from "next";
import Link from "next/link";

import { ActiveTrades, type PositionSummary } from "@/components/founder/ActiveTrades";
import { ClearPaperSymbolButton } from "@/components/founder/ClearPaperSymbolButton";
import { EmptyState, PageHeader, Panel } from "@/components/ui";
import { requireUser } from "@/lib/actions/auth";
import { money, moneyPnl, pnlClass } from "@/lib/founder/simple";
import { formatTimestamp } from "@/lib/format";
import { apiFetch } from "@/lib/server/api";
import { soft } from "@/lib/server/control-plane";

export const metadata: Metadata = { title: "Trades" };

type Portfolio = { id: string; name: string; kill_switch_active: boolean };
type ClosedTrade = {
  fill_id: string;
  symbol: string;
  quantity: string;
  entry_price: string;
  exit_price: string;
  realized_pnl: string;
  filled_at: string;
  exit_reason: string | null;
};
type Fill = {
  id: string;
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
    order_count?: number;
    win_rate?: string | null;
    exposure?: string | null;
  };
  report_date?: string;
};

export default async function TradesPage() {
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
  let positions: PositionSummary[] = [];
  let closed: ClosedTrade[] = [];
  let fills: Fill[] = [];
  if (portfolio) {
    const [p, c, f] = await Promise.all([
      soft(() =>
        apiFetch<PositionSummary[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/position-summaries`,
        ),
      ),
      soft(() =>
        apiFetch<ClosedTrade[]>(
          `/api/v1/paper/portfolios/${portfolio.id}/closed-trades`,
          { searchParams: { limit: 20 } },
        ),
      ),
      soft(() =>
        apiFetch<Fill[]>(`/api/v1/paper/portfolios/${portfolio.id}/fills`, {
          searchParams: { limit: 20 },
        }),
      ),
    ]);
    positions = p ?? [];
    closed = c ?? [];
    fills = f ?? [];
  }

  const report = reports?.[0];

  return (
    <>
      <PageHeader
        title="Trades"
        description="Open and closed paper trades. Simulated money only. Technical IDs stay under Advanced."
      />

      <div className="simple-row">
        <div className="simple-chip">
          <span className="metric-label">Status</span>
          <strong>
            {portfolio?.kill_switch_active ? "Emergency stop" : "Paper active"}
          </strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Profit or Loss Today</span>
          <strong className={pnlClass(report?.content?.daily_pnl ?? null)}>
            {report?.content?.daily_pnl != null
              ? moneyPnl(report.content.daily_pnl)
              : "Not reported yet"}
          </strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">
            Order Updates{" "}
            <span className="info-tip" title="Fill count from the latest saved report.">
              ?
            </span>
          </span>
          <strong>{report?.content?.trade_count ?? "—"}</strong>
        </div>
        <div className="simple-chip">
          <span className="metric-label">Money Currently in Trades</span>
          <strong>
            {report?.content?.exposure != null
              ? money(report.content.exposure)
              : "See open trades"}
          </strong>
        </div>
      </div>

      <Panel title="Open paper trades">
        <ActiveTrades
          positions={positions}
          portfolioId={portfolio?.id ?? null}
        />
      </Panel>

      <Panel title="Closed Trades">
        {closed.length === 0 ? (
          <EmptyState>
            No closed paper trades yet. Completed simulated trades will appear
            here with profit or loss.
          </EmptyState>
        ) : (
          <div className="open-trade-cards">
            {closed.map((t) => {
              const entry = Number(t.entry_price);
              const exit = Number(t.exit_price);
              const absurd =
                (t.symbol.toUpperCase().startsWith("BTC") &&
                  ((entry > 0 && entry < 1000) || (exit > 0 && exit < 1000))) ||
                (t.symbol.toUpperCase().startsWith("ETH") &&
                  ((entry > 0 && entry < 50) || (exit > 0 && exit < 50)));
              return (
              <article key={t.fill_id} className="open-trade-card">
                <header className="open-trade-head">
                  <h3>{t.symbol}</h3>
                  <span className={pnlClass(t.realized_pnl)}>
                    {moneyPnl(t.realized_pnl)}
                  </span>
                </header>
                {absurd ? (
                  <p className="attention-box" role="status">
                    This closed paper P&amp;L used inaccurate test prices. Remove
                    the {t.symbol} practice history and refresh real market data.
                  </p>
                ) : null}
                <dl className="considering-dl">
                  <div>
                    <dt>Entry</dt>
                    <dd>{money(t.entry_price)}</dd>
                  </div>
                  <div>
                    <dt>Exit</dt>
                    <dd>{money(t.exit_price)}</dd>
                  </div>
                  <div>
                    <dt>Quantity</dt>
                    <dd>{t.quantity}</dd>
                  </div>
                  <div>
                    <dt>When</dt>
                    <dd>{formatTimestamp(t.filled_at)}</dd>
                  </div>
                </dl>
                {t.exit_reason ? (
                  <p className="muted-note">Why Argus decided: {t.exit_reason}</p>
                ) : null}
                {portfolio && absurd ? (
                  <ClearPaperSymbolButton
                    portfolioId={portfolio.id}
                    symbol={t.symbol}
                  />
                ) : null}
              </article>
              );
            })}
          </div>
        )}
      </Panel>

      <details className="tech-details">
        <summary>Advanced details — Order Updates</summary>
        {fills.length === 0 ? (
          <EmptyState>No order updates yet.</EmptyState>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Asset</th>
                  <th>Side</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>When</th>
                </tr>
              </thead>
              <tbody>
                {fills.map((f) => (
                  <tr key={f.id}>
                    <td>{f.symbol}</td>
                    <td>{f.side}</td>
                    <td>{f.quantity}</td>
                    <td>{money(f.price)}</td>
                    <td>{formatTimestamp(f.filled_at)}</td>
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
        <Link className="btn" href="/paper-training">
          Argus Academy
        </Link>
        <Link className="btn secondary" href="/paper">
          Advanced paper details
        </Link>
      </div>
    </>
  );
}
