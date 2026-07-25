import { REJECTION_LABELS } from "@/lib/founder/decisionStream";

const STAGES = [
  ["scanned", "Scanned"],
  ["watching", "Watching"],
  ["qualified", "Qualified"],
  ["risk_review", "Risk Review"],
  ["approved", "Approved"],
  ["orders", "Orders"],
  ["positions", "Positions"],
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
    .slice(0, 8);

  return (
    <div className="decision-pipeline">
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
      <h3 className="section-subhead">Leading rejection reasons</h3>
      {rejectionRows.length === 0 ? (
        <p className="muted-note">
          No rejections recorded in the latest scan. Argus may still be waiting for
          instruments, bars, or the next cycle.
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
      <p className="muted-note" style={{ marginBottom: 0 }}>
        Zero new trades can still mean Argus is working — setups are being scanned
        and rejected for documented reasons.
      </p>
    </div>
  );
}
