"use client";

import { useState, useTransition } from "react";

import {
  emergencyRecoverAction,
  emergencyStopAction,
  initializeModeAction,
  transitionModeAction,
  type ActionResult,
} from "@/lib/actions/auth";
import type { OperatingModeState } from "@/lib/types";

export function ModeForms({
  kind,
  mode,
  enterable = [],
  canEmergency = false,
}: {
  kind: "initialize" | "manage";
  mode?: OperatingModeState;
  enterable?: string[];
  canEmergency?: boolean;
}) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  function run(action: (fd: FormData) => Promise<ActionResult>, form: HTMLFormElement) {
    const fd = new FormData(form);
    startTransition(async () => {
      const res = await action(fd);
      setResult(res);
      if (res.ok) {
        window.location.reload();
      }
    });
  }

  if (kind === "initialize") {
    return (
      <form
        onSubmit={(e) => {
          e.preventDefault();
          startTransition(async () => {
            const res = await initializeModeAction();
            setResult(res);
            if (res.ok) window.location.reload();
          });
        }}
      >
        <p style={{ color: "var(--muted)" }}>
          System mode state is missing. Founder may initialize the operating-mode
          machine.
        </p>
        {result ? (
          <div className={`alert ${result.ok ? "ok" : "error"}`} role="status">
            {result.message}
          </div>
        ) : null}
        <button className="btn" type="submit" disabled={pending}>
          {pending ? "Initializing…" : "Initialize operating mode"}
        </button>
      </form>
    );
  }

  return (
    <div>
      {result ? (
        <div className={`alert ${result.ok ? "ok" : "error"}`} role="status">
          {result.message}
        </div>
      ) : null}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (
            !window.confirm(
              "Confirm operating-mode transition? This is an institutional control action.",
            )
          ) {
            return;
          }
          run(transitionModeAction, e.currentTarget);
        }}
      >
        <input
          type="hidden"
          name="expected_state_version"
          value={mode?.state_version ?? ""}
        />
        <div className="field">
          <label htmlFor="target_mode">Target mode</label>
          <select id="target_mode" name="target_mode" required disabled={pending}>
            <option value="">Select enterable target</option>
            {enterable.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="reason">Reason</label>
          <textarea id="reason" name="reason" rows={3} required disabled={pending} />
        </div>
        <button className="btn" type="submit" disabled={pending || enterable.length === 0}>
          Transition mode
        </button>
      </form>

      {canEmergency ? (
        <div style={{ marginTop: "1.25rem", display: "grid", gap: "1rem" }}>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (
                !window.confirm(
                  "Confirm EMERGENCY STOP? This is a Founder-only protective action.",
                )
              ) {
                return;
              }
              run(emergencyStopAction, e.currentTarget);
            }}
          >
            <input
              type="hidden"
              name="expected_state_version"
              value={mode?.state_version ?? ""}
            />
            <div className="field">
              <label htmlFor="em_reason">Emergency stop reason</label>
              <textarea
                id="em_reason"
                name="reason"
                rows={2}
                required
                disabled={pending}
              />
            </div>
            <button className="btn danger" type="submit" disabled={pending}>
              Emergency stop
            </button>
          </form>

          {mode?.emergency_stop_active || mode?.recovery_required ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!window.confirm("Confirm emergency recovery?")) return;
                run(emergencyRecoverAction, e.currentTarget);
              }}
            >
              <input
                type="hidden"
                name="expected_state_version"
                value={mode?.state_version ?? ""}
              />
              <div className="field">
                <label htmlFor="rec_reason">Recovery reason</label>
                <textarea
                  id="rec_reason"
                  name="reason"
                  rows={2}
                  required
                  disabled={pending}
                />
              </div>
              <button className="btn secondary" type="submit" disabled={pending}>
                Recover from emergency stop
              </button>
            </form>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
