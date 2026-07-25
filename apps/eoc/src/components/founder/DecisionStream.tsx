"use client";

import { useEffect, useState } from "react";

import { EmptyState } from "@/components/ui";
import type { DecisionItem } from "@/lib/founder/decisionStream";
import { formatTimestamp } from "@/lib/format";

export function DecisionStream({
  initialItems,
  pollMs = 15_000,
}: {
  initialItems: DecisionItem[];
  pollMs?: number;
}) {
  const [items, setItems] = useState(initialItems);
  const [showTechnical, setShowTechnical] = useState(false);

  useEffect(() => {
    setItems(initialItems);
  }, [initialItems]);

  useEffect(() => {
    let cancelled = false;
    async function tick() {
      try {
        const res = await fetch("/api/founder/decisions", { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as { items?: DecisionItem[] };
        if (!cancelled && Array.isArray(data.items)) setItems(data.items);
      } catch {
        /* keep last good snapshot */
      }
    }
    const id = window.setInterval(tick, pollMs);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollMs]);

  if (items.length === 0) {
    return (
      <EmptyState>
        No market or trading decisions yet. Technical supervisor noise is hidden
        here by default.
      </EmptyState>
    );
  }

  return (
    <div>
      <ul className="activity-feed">
        {items.map((item) => (
          <li key={item.id} className={`activity-item activity-${item.tone}`}>
            <div className="activity-when">{formatTimestamp(item.at)}</div>
            <div className="activity-title">
              {item.symbol ? `${item.symbol} · ` : ""}
              {item.event}
            </div>
            <div className="activity-detail">
              Outcome: {item.outcome}
              {item.reason ? ` — ${item.reason}` : ""}
              {item.strategy ? ` · ${item.strategy}` : ""}
            </div>
            {showTechnical && item.correlationId ? (
              <div className="activity-detail">Trace {item.correlationId}</div>
            ) : null}
          </li>
        ))}
      </ul>
      <button
        type="button"
        className="btn secondary"
        style={{ marginTop: "0.75rem" }}
        onClick={() => setShowTechnical((v) => !v)}
      >
        {showTechnical ? "Hide technical IDs" : "Show technical IDs"}
      </button>
    </div>
  );
}
