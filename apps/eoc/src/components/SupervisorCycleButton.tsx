"use client";

import { useState, useTransition } from "react";

import {
  runSupervisorCycleAction,
  type ActionResult,
} from "@/lib/actions/auth";

export function SupervisorCycleButton() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <div>
      {result ? (
        <div
          className={`alert ${result.ok ? "ok" : "error"}`}
          role="status"
          style={{ marginBottom: "0.5rem" }}
        >
          {result.message}
        </div>
      ) : null}
      <button
        type="button"
        className="btn secondary"
        disabled={pending}
        onClick={() => {
          if (!window.confirm("Run a supervisor evaluation cycle now?")) return;
          startTransition(async () => {
            const res = await runSupervisorCycleAction();
            setResult(res);
            if (res.ok) window.location.reload();
          });
        }}
      >
        {pending ? "Running…" : "Run supervisor cycle"}
      </button>
    </div>
  );
}
