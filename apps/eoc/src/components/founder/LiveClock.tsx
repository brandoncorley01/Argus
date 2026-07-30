"use client";

import { useEffect, useState } from "react";

import { formatLiveClock } from "@/lib/format";

/** Ticking Eastern clock — null until mount to avoid SSR hydration mismatch. */
export function LiveClock({
  className,
  prefix = "",
}: {
  className?: string;
  prefix?: string;
}) {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    setNow(Date.now());
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const label = now == null ? "—" : formatLiveClock(now);

  return (
    <time
      className={className ?? "argus-live-clock"}
      dateTime={now == null ? undefined : new Date(now).toISOString()}
      aria-live="polite"
      aria-atomic="true"
      title="US Eastern"
    >
      {prefix}
      {label}
    </time>
  );
}
