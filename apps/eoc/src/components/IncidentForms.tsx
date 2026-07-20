"use client";

import { useState, useTransition } from "react";

import {
  createIncidentAction,
  transitionIncidentAction,
  type ActionResult,
} from "@/lib/actions/auth";

export function IncidentCreateForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await createIncidentAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      {result ? (
        <div className={`alert ${result.ok ? "ok" : "error"}`} role="status">
          {result.message}
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="title">Title</label>
        <input id="title" name="title" required disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="description">Description</label>
        <textarea id="description" name="description" rows={3} disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="severity">Severity</label>
        <select id="severity" name="severity" defaultValue="medium" disabled={pending}>
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
          <option value="critical">critical</option>
        </select>
      </div>
      <button className="btn" type="submit" disabled={pending}>
        Open incident
      </button>
    </form>
  );
}

export function IncidentTransitionForm({ incidentId }: { incidentId: string }) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!window.confirm("Confirm incident lifecycle transition?")) return;
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await transitionIncidentAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <input type="hidden" name="incident_id" value={incidentId} />
      {result ? (
        <div className={`alert ${result.ok ? "ok" : "error"}`} role="status">
          {result.message}
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="target_status">Target status</label>
        <select id="target_status" name="target_status" required disabled={pending}>
          <option value="investigating">investigating</option>
          <option value="mitigated">mitigated</option>
          <option value="closed">closed</option>
          <option value="open">open</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="note">Note</label>
        <textarea id="note" name="note" rows={2} disabled={pending} />
      </div>
      <button className="btn" type="submit" disabled={pending}>
        Transition
      </button>
    </form>
  );
}
