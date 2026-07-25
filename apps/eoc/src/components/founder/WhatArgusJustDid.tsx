"use client";

import { useState } from "react";

import { EmptyState } from "@/components/ui";
import type { TimelineItem } from "@/lib/founder/justDidTimeline";
import { formatTimestamp } from "@/lib/format";

export type { TimelineItem };

export function WhatArgusJustDid({ items }: { items: TimelineItem[] }) {
  const [showAdvanced, setShowAdvanced] = useState(false);

  if (items.length === 0) {
    return (
      <EmptyState>
        No recent decisions yet. After Argus scans markets, a short timeline of
        what it just did will appear here.
      </EmptyState>
    );
  }

  return (
    <div className="just-did">
      <ol className="just-did-list">
        {items.map((item) => (
          <li key={item.id}>
            <time dateTime={item.at}>{formatTimestamp(item.at)}</time>
            <span>{item.text}</span>
            {showAdvanced && item.advanced ? (
              <pre className="tech-details">{item.advanced}</pre>
            ) : null}
          </li>
        ))}
      </ol>
      <button
        type="button"
        className="btn secondary"
        onClick={() => setShowAdvanced((v) => !v)}
      >
        {showAdvanced ? "Hide advanced details" : "Advanced details"}
      </button>
    </div>
  );
}
