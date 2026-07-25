import { REJECTION_LABELS } from "@/lib/founder/decisionStream";

const STAGES = [
  ["scanned", "Looked at"],
  ["watching", "Watching"],
  ["qualified", "Passed checks"],
  ["risk_review", "Risk check"],
  ["approved", "Approved"],
  ["orders", "Orders"],
  ["positions", "Open now"],
] as const;

export function DecisionPipeline({
  counts,
  rejections,
}: {
  counts: Record<string, number>;
  rejections: Record<string, number>;
}) {
  const rejectionRows = Object.entries(rejections)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5);

  return (
    <div className="decision-pipeline">
      <p className="muted-note" style={{ marginTop: 0 }}>
        How the last scan sorted markets. Zeros here usually mean “looked, then passed”
        — not that Argus is broken.
      </p>
      <div className="pipeline-row" aria-label="Decision pipeline counts">
        {STAGES.map(([key, label], idx) => (
          <div key={key} className="pipeline-step">
            {idx > 0 ? <span className="pipeline-arrow">→</span> : null}
            <div className="pipeline-chip">
              <span className="metric-label">{label}</span>
              <strong>{counts[key] ?? 0}</strong>
            </div>
          </div>
        ))}
      </div>
      <h3 className="section-subhead">Why setups were skipped</h3>
      {rejectionRows.length === 0 ? (
        <p className="muted-note">
          No skip reasons yet. Run a scan after instruments and price bars exist.
        </p>
      ) : (
        <ul className="plain-list rejection-list">
          {rejectionRows.map(([code, n]) => (
            <li key={code}>
              <strong>{REJECTION_LABELS[code] ?? code}</strong>: {n}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
