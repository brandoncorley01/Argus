import type { ReactNode } from "react";

import { healthTone } from "@/lib/format";

export function StatusBadge({
  status,
  label,
}: {
  status?: string | null;
  label?: string;
}) {
  const tone = healthTone(status);
  return (
    <span className={`badge ${tone}`}>
      <span aria-hidden="true">●</span>
      {label ?? status ?? "unavailable"}
    </span>
  );
}

export function Panel({
  title,
  children,
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`panel rise ${className}`.trim()}>
      {title ? <h2>{title}</h2> : null}
      {children}
    </section>
  );
}

export function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="metric">
      <span className="metric-label">{label}</span>
      <span className="metric-value">{value}</span>
      {hint ? (
        <span style={{ color: "var(--muted)", fontSize: "0.85rem" }}>{hint}</span>
      ) : null}
    </div>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="state-block">{children}</div>;
}

export function ErrorState({ children }: { children: ReactNode }) {
  return (
    <div className="state-block error" role="alert">
      {children}
    </div>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-header rise">
      <div>
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
      {actions ? <div className="form-actions">{actions}</div> : null}
    </header>
  );
}
