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
  strategy_by_regime?: Array<{
    strategy_key: string;
    market_regime: string;
    trades: number;
    wins: number;
    win_rate: string | null;
    net_pnl_after_costs: string | null;
    expectancy_after_costs?: string | null;
  }>;
  pattern_performance?: Array<{
    pattern: string;
    trades: number;
    wins: number;
    win_rate: string | null;
    net_pnl_after_costs: string | null;
  }>;
  high_volume_learning_summary?: {
    findings?: string;
    volume_never_triggers_trade?: boolean;
    market_quality_note?: string;
    high_volume_symbols?: Array<{
      symbol: string;
      relative_volume: number | null;
      analysis_priority: number;
      stage?: string;
      liquidity_ok?: boolean | null;
      volatility_pct?: number | null;
      spread_proxy_pct?: number | null;
      activity_notional?: number | null;
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
  good_vs_lucky?: {
    good_decision_wins?: number;
    lucky_or_unlabeled_wins?: number;
    poor_decision_losses?: number;
  };
  confidence_calibration?: {
    sample_size?: number;
    high_confidence_win_rate?: string | null;
    low_confidence_win_rate?: string | null;
    higher_confidence_better?: boolean | null;
    note?: string;
  };
  missed_and_rejected?: {
    rejected_that_became_winners?: number;
    accepted_that_became_losers?: number;
    strongest_conditions?: string | null;
    weakest_conditions?: string | null;
    note?: string;
  };
  readiness_report?: {
    summary: string;
    ready_for_controlled_live_testing: boolean;
    live_trading_enabled: boolean;
    body?: Record<string, unknown>;
  } | null;
  knowledge_retained?: number | null;
  knowledge_reused?: number | null;
  memory_reuse_rate?: string | null;
  explained_loss_pct?: string | null;
  decision_quality?: {
    GOOD_DECISION_WIN?: number;
    GOOD_DECISION_LOSS?: number;
    POOR_DECISION_WIN?: number;
    POOR_DECISION_LOSS?: number;
    good_decision_rate?: string | null;
    good_decision_wins?: number;
    lucky_or_unlabeled_wins?: number;
    poor_decision_losses?: number;
  };
  learning_velocity?: string | null;
  maximum_drawdown_pct_of_start?: string | null;
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
  const byRegime = data.strategy_by_regime ?? [];
  const patterns = data.pattern_performance ?? [];
  const gvl = data.good_vs_lucky;
  const cal = data.confidence_calibration;
  const missed = data.missed_and_rejected;

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

      <div className="summary-grid summary-grid-primary" style={{ marginTop: "0.75rem" }}>
        <div className="summary-card">
          <span className="metric-label">Knowledge Retained</span>
          <strong>{data.knowledge_retained ?? "—"}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Knowledge Reused</span>
          <strong>{data.knowledge_reused ?? "—"}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Memory Reuse Rate</span>
          <strong>{pct(data.memory_reuse_rate)}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Explained Loss %</span>
          <strong>{pct(data.explained_loss_pct)}</strong>
        </div>
        <div className="summary-card">
          <span className="metric-label">Decision Quality</span>
          <strong>
            {pct(data.decision_quality?.good_decision_rate)}
          </strong>
          <span className="muted-note" style={{ display: "block", marginTop: "0.25rem" }}>
            G/W {data.decision_quality?.GOOD_DECISION_WIN ?? data.decision_quality?.good_decision_wins ?? 0}
            {" · "}
            G/L {data.decision_quality?.GOOD_DECISION_LOSS ?? 0}
            {" · "}
            P/W {data.decision_quality?.POOR_DECISION_WIN ?? data.decision_quality?.lucky_or_unlabeled_wins ?? 0}
            {" · "}
            P/L {data.decision_quality?.POOR_DECISION_LOSS ?? data.decision_quality?.poor_decision_losses ?? 0}
          </span>
        </div>
        <div className="summary-card">
          <span className="metric-label">Learning Velocity</span>
          <strong>{num(data.learning_velocity, 2)}</strong>
        </div>
      </div>

      <div className="readiness-box" role="status" style={{ marginTop: "0.85rem" }}>
        <strong>
          Expectancy after fees: {moneyPnl(data.expectancy_after_costs)}
        </strong>
        <p className="muted-note" style={{ margin: "0.35rem 0 0" }}>
          Cost model {data.cost_model_bps_each_way ?? "10"} bps each way on top of
          paper fill fees/slippage. Program status: {data.program_status ?? "active"}.
          {data.maximum_drawdown_pct_of_start != null
            ? ` Drawdown vs $300 start: ${pct(data.maximum_drawdown_pct_of_start)}.`
            : ""}
          {" "}Prior lessons now gate automatic paper entries (EXECUTE / WAIT / AVOID).
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

      <h3>Strategy × Market Conditions</h3>
      {byRegime.length === 0 ? (
        <p className="muted-note">
          Regime breakdown appears after closed trades with market regime labels.
        </p>
      ) : (
        <div className="table-wrap">
          <table className="data">
            <thead>
              <tr>
                <th>Strategy</th>
                <th>Regime</th>
                <th>Trades</th>
                <th>Win rate</th>
                <th>Net after costs</th>
              </tr>
            </thead>
            <tbody>
              {byRegime.slice(0, 10).map((row) => (
                <tr key={`${row.strategy_key}-${row.market_regime}`}>
                  <td>{row.strategy_key}</td>
                  <td>{row.market_regime}</td>
                  <td>
                    {row.wins}/{row.trades}
                  </td>
                  <td>{pct(row.win_rate)}</td>
                  <td className={pnlClass(row.net_pnl_after_costs)}>
                    {moneyPnl(row.net_pnl_after_costs)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3>Pattern Evidence</h3>
      {patterns.length === 0 ? (
        <p className="muted-note">
          Momentum, breakout, dip, range, and peak labels appear from trade evidence.
        </p>
      ) : (
        <ul className="closed-lessons">
          {patterns.slice(0, 8).map((p) => (
            <li key={p.pattern}>
              <strong>{p.pattern}</strong> — {p.wins}/{p.trades} wins (
              {pct(p.win_rate)}){" "}
              <span className={pnlClass(p.net_pnl_after_costs)}>
                {moneyPnl(p.net_pnl_after_costs)}
              </span>
            </li>
          ))}
        </ul>
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
      {volume?.market_quality_note ? (
        <p className="muted-note">{volume.market_quality_note}</p>
      ) : null}
      {(volume?.high_volume_symbols?.length ?? 0) > 0 ? (
        <ul className="closed-lessons">
          {volume!.high_volume_symbols!.slice(0, 6).map((s) => (
            <li key={s.symbol}>
              {s.symbol} — priority {s.analysis_priority}
              {s.relative_volume != null
                ? ` · rel vol ${s.relative_volume.toFixed(2)}×`
                : ""}
              {s.liquidity_ok === true
                ? " · liquid"
                : s.liquidity_ok === false
                  ? " · thin"
                  : ""}
              {s.volatility_pct != null
                ? ` · vol ${s.volatility_pct.toFixed(2)}%`
                : ""}
              {s.spread_proxy_pct != null
                ? ` · spread≈${s.spread_proxy_pct.toFixed(2)}%`
                : ""}
              {s.stage ? ` · ${s.stage}` : ""}
            </li>
          ))}
        </ul>
      ) : null}

      <h3>Good Decisions vs Lucky Wins</h3>
      {gvl ? (
        <ul className="closed-lessons">
          <li>Good-decision wins: {gvl.good_decision_wins ?? 0}</li>
          <li>
            Lucky or unlabeled wins: {gvl.lucky_or_unlabeled_wins ?? 0}
          </li>
          <li>Poor-decision losses: {gvl.poor_decision_losses ?? 0}</li>
        </ul>
      ) : (
        <p className="muted-note">Decision-quality labels appear after reviews.</p>
      )}

      <h3>Confidence Calibration</h3>
      {cal ? (
        <>
          <ul className="closed-lessons">
            <li>Sample size: {cal.sample_size ?? 0}</li>
            <li>High-confidence win rate: {pct(cal.high_confidence_win_rate)}</li>
            <li>Low-confidence win rate: {pct(cal.low_confidence_win_rate)}</li>
            <li>
              Higher confidence better:{" "}
              {cal.higher_confidence_better == null
                ? "—"
                : cal.higher_confidence_better
                  ? "yes"
                  : "no"}
            </li>
          </ul>
          {cal.note ? <p className="muted-note">{cal.note}</p> : null}
        </>
      ) : (
        <p className="muted-note">Calibration needs closed paper trades.</p>
      )}

      <h3>Missed &amp; Rejected</h3>
      {missed ? (
        <>
          <ul className="closed-lessons">
            <li>
              Rejected that became winners:{" "}
              {missed.rejected_that_became_winners ?? 0}
            </li>
            <li>
              Accepted that became losers:{" "}
              {missed.accepted_that_became_losers ?? 0}
            </li>
            <li>
              Strongest conditions: {missed.strongest_conditions ?? "—"}
            </li>
            <li>Weakest conditions: {missed.weakest_conditions ?? "—"}</li>
          </ul>
          {missed.note ? <p className="muted-note">{missed.note}</p> : null}
        </>
      ) : (
        <p className="muted-note">Missed-opportunity tracking fills from radar rejects.</p>
      )}

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
