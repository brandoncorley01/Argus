"use client";

import { money, moneyPnl, pnlClass } from "@/lib/founder/simple";

export type AdvancedLearningPaneData = {
  learning_day?: number;
  required_days?: number;
  program_status?: string;
  net_paper_profit?: string | null;
  today_pnl?: string | null;
  win_rate?: string | null;
  profit_factor?: string | null;
  maximum_drawdown?: string | null;
  leading_strategy?: string | null;
  best_performing_coin?: string | null;
  learning_confidence?: string | null;
  readiness_score?: string | null;
  expectancy_after_costs?: string | null;
  cost_model_bps_each_way?: string | null;
  strategy_leaderboard?: Array<{
    strategy_key: string;
    trades: number;
    wins: number;
    win_rate: string | null;
    net_pnl_after_costs: string | null;
    paper_confidence_delta: string | null;
  }>;
  high_volume_learning_summary?: {
    findings?: string;
    volume_never_triggers_trade?: boolean;
    high_volume_symbols?: Array<{
      symbol: string;
      relative_volume: number | null;
      analysis_priority: number;
      stage?: string;
    }>;
    priority_queue?: Array<{
      symbol: string;
      analysis_priority: number;
      relative_volume: number | null;
    }>;
  };
  recent_trade_lessons?: Array<{
    id: string;
    at: string;
    symbol: string;
    outcome: string;
    net_after_costs: string | null;
    pattern: string;
    lesson: string;
    good_decision: boolean | null;
  }>;
  learning_milestones?: Array<{
    key: string;
    title: string;
    achieved: boolean;
    achieved_at: string | null;
  }>;
  readiness_report?: {
    summary: string;
    ready_for_controlled_live_testing: boolean;
    live_trading_enabled: boolean;
    body?: Record<string, unknown>;
  } | null;
  disclaimer?: string;
  error?: string;
  live_trading_enabled?: boolean;
};

function pct(value: string | null | undefined): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(0)}%`;
}

function num(value: string | null | undefined, digits = 1): string {
  if (value == null || value === "") return "—";
  const n = Number(value);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

/** Advanced Learning pane — preserves Argus panel/card visual language. */
export function AdvancedLearningPane({
  data,
}: {
  data: AdvancedLearningPaneData | null;
}) {
  if (!data) {
    return (
      <section className="panel rise" aria-label="Advanced Learning">
        <h2 style={{ marginTop: 0 }}>Advanced Learning</h2>
        <p className="muted-note">
          Learning pane unavailable. Start Argus so paper reviews can feed the
          20-day engine.
        </p>
      </section>
    );
  }

  const day = data.learning_day ?? 1;
  const need = data.required_days ?? 20;
  const volume = data.high_volume_learning_summary;
  const milestones = data.learning_milestones ?? [];
  const lessons = data.recent_trade_lessons ?? [];
  const board = data.strategy_leaderboard ?? [];

  return (
    <section className="panel rise" aria-label="Advanced Learning">
      <h2 style={{ marginTop: 0 }}>Advanced Learning</h2>
      <p className="muted-note">
        20-day PAPER learning engine. Opportunity Radar feeds analysis priority.
        High volume never alone triggers a trade. Live trading stays locked.
      </p>
      {data.error ? (
        <p className="attention-box" role="status">
          {data.error}
        </p>
      ) : null}

      <div className="summary-grid summary-grid-primary">
        <div className="summary-card">
          <span className="metric-label">Learning Day</span>
          <strong>
            {day} of {need}
          </strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Net Paper Profit</span>
          <strong className={pnlClass(data.net_paper_profit)}>
            {moneyPnl(data.net_paper_profit)}
          </strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Today&apos;s P&amp;L</span>
          <strong className={pnlClass(data.today_pnl)}>
            {moneyPnl(data.today_pnl)}
          </strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Win Rate</span>
          <strong>{pct(data.win_rate)}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Profit Factor</span>
          <strong>{num(data.profit_factor, 2)}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Maximum Drawdown</span>
          <strong>{money(data.maximum_drawdown)}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Leading Strategy</span>
          <strong>{data.leading_strategy ?? "—"}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Best-Performing Coin</span>
          <strong>{data.best_performing_coin ?? "—"}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Learning Confidence</span>
          <strong>{num(data.learning_confidence, 0)}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Readiness Score</span>
          <strong>{num(data.readiness_score, 0)}</strong>
        </div>
      </div>

      <div className="readiness-box" role="status" style={{ marginTop: "0.85rem" }}>
        <strong>
          Expectancy after fees: {moneyPnl(data.expectancy_after_costs)}
        </strong>
        <p className="muted-note" style={{ margin: "0.35rem 0 0" }}>
          Cost model {data.cost_model_bps_each_way ?? "10"} bps each way on top of
          paper fill fees/slippage. Program status: {data.program_status ?? "active"}.
        </p>
      </div>

      <h3>Strategy Leaderboard</h3>
      {board.length === 0 ? (
        <p className="muted-note">No closed paper strategies in this cycle yet.</p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Trades</th>
                <th>Win rate</th>
                <th>Net after costs</th>
                <th>PAPER Δ conf</th>
              </tr>
            </thead>
            <tbody>
              {board.map((row) => (
                <tr key={row.strategy_key}>
                  <td>{row.strategy_key}</td>
                  <td>
                    {row.wins}/{row.trades}
                  </td>
                  <td>{pct(row.win_rate)}</td>
                  <td className={pnlClass(row.net_pnl_after_costs)}>
                    {moneyPnl(row.net_pnl_after_costs)}
                  </td>
                  <td>{row.paper_confidence_delta ?? "0"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>High-Volume Learning Summary</h3>
      <p className="muted-note">
        {volume?.findings ??
          "Opportunity Radar volume inputs appear once markets are scanning."}
      </p>
      <p className="muted-note">
        Volume never triggers a trade
        {volume?.volume_never_triggers_trade === false ? " (misconfigured)" : " ✓"}.
      </p>
      {(volume?.high_volume_symbols?.length ?? 0) > 0 ? (
        <ul className="closed-lessons">
          {volume!.high_volume_symbols!.slice(0, 6).map((s) => (
            <li key={s.symbol}>
              {s.symbol} — priority {s.analysis_priority}
              {s.relative_volume != null
                ? ` · rel vol ${s.relative_volume.toFixed(2)}×`
                : ""}
              {s.stage ? ` · ${s.stage}` : ""}
            </li>
          ))}
        </ul>
      ) : null}

      <h3>Recent Trade Lessons</h3>
      {lessons.length === 0 ? (
        <p className="muted-note">Lessons appear after closed paper trades.</p>
      ) : (
        <ul className="closed-lessons">
          {lessons.slice(0, 8).map((l) => (
            <li key={l.id}>
              <strong>{l.symbol}</strong> ({l.pattern}, {l.outcome}){" "}
              <span className={pnlClass(l.net_after_costs)}>
                {moneyPnl(l.net_after_costs)}
              </span>
              {l.good_decision === true
                ? " · good decision"
                : l.good_decision === false
                  ? " · review decision quality"
                  : ""}
              <div className="muted-note">{l.lesson}</div>
            </li>
          ))}
        </ul>
      )}

      <h3>Learning Milestones</h3>
      <ul className="closed-lessons" aria-label="Learning milestones">
        {milestones.map((m) => (
          <li key={m.key}>
            <span className={`decision-pill ${m.achieved ? "stage-ok" : ""}`}>
              {m.achieved ? "Done" : "Open"}
            </span>{" "}
            {m.title}
            {m.achieved_at ? (
              <span className="muted-note"> — {m.achieved_at.slice(0, 10)}</span>
            ) : null}
          </li>
        ))}
      </ul>

      {data.readiness_report ? (
        <div className="readiness-box" style={{ marginTop: "0.85rem" }}>
          <h3 style={{ marginTop: 0 }}>Day-20 Readiness Report</h3>
          <p>{data.readiness_report.summary}</p>
          <p className="muted-note">
            Ready for controlled live testing review:{" "}
            {data.readiness_report.ready_for_controlled_live_testing ? "yes" : "no"}.
            Live trading enabled: never (always false).
          </p>
        </div>
      ) : (
        <p className="muted-note" style={{ marginTop: "0.75rem" }}>
          Readiness Report generates automatically after Learning Day {need} from
          stored evidence — it never enables live trading.
        </p>
      )}

      <p className="muted-note" style={{ marginTop: "0.75rem" }}>
        {data.disclaimer ??
          "Profit is the mission. Risk discipline protects the mission. Advanced learning improves the mission."}
      </p>
    </section>
  );
}
