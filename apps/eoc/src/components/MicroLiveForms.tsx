"use client";

import { useState, useTransition } from "react";

import {
  createCredentialReferenceAction,
  createReconciliationRunAction,
  dryRunValidateOrderAction,
  putCapitalPolicyAction,
  setKillSwitchAction,
  transitionActivationAction,
  validateCredentialReferenceAction,
} from "@/lib/actions/micro-live";
import type { ActionResult } from "@/lib/actions/auth";
import type { DryRunOrderResult, MicroCapitalPolicy } from "@/lib/types";

function ResultBanner({ result }: { result: ActionResult | null }) {
  if (!result) return null;
  return (
    <div className={`alert ${result.ok ? "ok" : "error"}`} role="status">
      {result.message}
    </div>
  );
}

/** Founder-only. Transition matrix and credential gates are enforced server-side. */
export function ActivationTransitionForm({
  currentState,
}: {
  currentState: string;
}) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (
          !window.confirm(
            "Confirm live-activation state transition? There is no reachable path to MICRO_LIVE_ACTIVE in this system; the backend will refuse it regardless of this form.",
          )
        ) {
          return;
        }
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await transitionActivationAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
        Current state: <strong>{currentState}</strong>
      </p>
      <div className="field">
        <label htmlFor="target_state">Target state</label>
        <select id="target_state" name="target_state" required disabled={pending}>
          <option value="">Select target</option>
          <option value="DISABLED">DISABLED</option>
          <option value="PAPER_ONLY">PAPER_ONLY</option>
          <option value="ADAPTER_CONFIGURED">ADAPTER_CONFIGURED</option>
          <option value="CREDENTIAL_REFERENCE_CONFIGURED">
            CREDENTIAL_REFERENCE_CONFIGURED
          </option>
          <option value="CONNECTION_VERIFIED">CONNECTION_VERIFIED</option>
          <option value="OBSERVE_ONLY">OBSERVE_ONLY</option>
          <option value="SANDBOX_OR_TESTNET">SANDBOX_OR_TESTNET</option>
          <option value="SHADOW_MODE">SHADOW_MODE</option>
          <option value="MICRO_LIVE_ARMED">MICRO_LIVE_ARMED</option>
          <option value="MICRO_LIVE_ACTIVE">MICRO_LIVE_ACTIVE (always refused)</option>
          <option value="SUSPENDED">SUSPENDED</option>
          <option value="EMERGENCY_STOP">EMERGENCY_STOP</option>
          <option value="RECOVERY">RECOVERY</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="reason">Reason</label>
        <textarea id="reason" name="reason" rows={2} required disabled={pending} />
      </div>
      <button className="btn" type="submit" disabled={pending}>
        {pending ? "Submitting…" : "Submit transition"}
      </button>
    </form>
  );
}

export function CredentialReferenceCreateForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await createCredentialReferenceAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
        Only an environment-variable NAME is stored. No secret value is ever
        accepted here or by the API.
      </p>
      <div className="field">
        <label htmlFor="provider_key">Provider key</label>
        <input
          id="provider_key"
          name="provider_key"
          placeholder="coinbase_adapter"
          required
          disabled={pending}
        />
      </div>
      <div className="field">
        <label htmlFor="ref_name">Env var reference name</label>
        <input
          id="ref_name"
          name="ref_name"
          placeholder="COINBASE_API_KEY_REF"
          required
          disabled={pending}
        />
      </div>
      <div className="field">
        <label htmlFor="purpose">Purpose</label>
        <input id="purpose" name="purpose" required disabled={pending} />
      </div>
      <button className="btn" type="submit" disabled={pending}>
        Register reference
      </button>
    </form>
  );
}

export function CredentialReferenceValidateButton({
  referenceId,
}: {
  referenceId: string;
}) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await validateCredentialReferenceAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
      style={{ display: "inline" }}
    >
      <input type="hidden" name="reference_id" value={referenceId} />
      <button className="btn secondary" type="submit" disabled={pending}>
        {pending ? "Checking…" : "Check presence"}
      </button>
      {result ? (
        <span
          style={{ marginLeft: "0.5rem", fontSize: "0.8rem" }}
          className={result.ok ? "" : "error"}
        >
          {result.message}
        </span>
      ) : null}
    </form>
  );
}

export function KillSwitchForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!window.confirm("Confirm kill switch change?")) return;
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await setKillSwitchAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      <div className="field">
        <label htmlFor="scope_type">Scope type</label>
        <select id="scope_type" name="scope_type" required disabled={pending}>
          <option value="global">global</option>
          <option value="provider">provider</option>
          <option value="account">account</option>
          <option value="portfolio">portfolio</option>
          <option value="strategy">strategy</option>
          <option value="instrument">instrument</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="scope_id">Scope id (blank for global)</label>
        <input id="scope_id" name="scope_id" disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="reason">Reason</label>
        <textarea id="reason" name="reason" rows={2} disabled={pending} />
      </div>
      <div className="field" style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}>
        <input id="active" name="active" type="checkbox" disabled={pending} />
        <label htmlFor="active" style={{ margin: 0 }}>
          Active (blocks execution for this scope)
        </label>
      </div>
      <button className="btn danger" type="submit" disabled={pending}>
        Apply kill switch
      </button>
    </form>
  );
}

export function CapitalPolicyForm({ policy }: { policy: MicroCapitalPolicy | null }) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await putCapitalPolicyAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      {(
        [
          ["max_deployable_capital", "Max deployable capital"],
          ["max_order_notional", "Max order notional"],
          ["max_daily_loss", "Max daily loss"],
          ["max_concurrent_exposure", "Max concurrent exposure"],
          ["max_provider_exposure", "Max provider exposure"],
          ["max_strategy_exposure", "Max strategy exposure"],
        ] as const
      ).map(([name, label]) => (
        <div className="field" key={name}>
          <label htmlFor={name}>{label}</label>
          <input
            id={name}
            name={name}
            type="text"
            inputMode="decimal"
            defaultValue={policy ? String(policy[name]) : ""}
            required
            disabled={pending}
          />
        </div>
      ))}
      <button className="btn" type="submit" disabled={pending}>
        Save policy (new version)
      </button>
    </form>
  );
}

export function ReconciliationRunForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await createReconciliationRunAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
        Fixture-based comparison only. No provider network call is made.
      </p>
      <div className="field">
        <label htmlFor="provider_key">Provider key</label>
        <input id="provider_key" name="provider_key" required disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="authoritative_state">Authoritative (paper) state — JSON</label>
        <textarea
          id="authoritative_state"
          name="authoritative_state"
          rows={3}
          required
          disabled={pending}
          defaultValue='{"cash": "1000", "positions": []}'
        />
      </div>
      <div className="field">
        <label htmlFor="comparison_state">Comparison state — JSON</label>
        <textarea
          id="comparison_state"
          name="comparison_state"
          rows={3}
          required
          disabled={pending}
          defaultValue='{"cash": "1000", "positions": []}'
        />
      </div>
      <button className="btn" type="submit" disabled={pending}>
        Run reconciliation
      </button>
    </form>
  );
}

export function DryRunOrderForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [dryRunResult, setDryRunResult] = useState<DryRunOrderResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await dryRunValidateOrderAction(new FormData(form));
          setResult(res);
          setDryRunResult(res.result ?? null);
        });
      }}
    >
      <ResultBanner result={result} />
      <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
        Validates against the active micro-capital policy only. Never submits
        an order to any provider.
      </p>
      <div className="field">
        <label htmlFor="quantity">Quantity</label>
        <input id="quantity" name="quantity" type="text" inputMode="decimal" required disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="reference_price">Reference price</label>
        <input
          id="reference_price"
          name="reference_price"
          type="text"
          inputMode="decimal"
          required
          disabled={pending}
        />
      </div>
      <button className="btn secondary" type="submit" disabled={pending}>
        {pending ? "Validating…" : "Dry-run validate"}
      </button>
      {dryRunResult ? (
        <dl style={{ marginTop: "0.75rem", display: "grid", gap: "0.35rem" }}>
          <div>
            <dt className="metric-label">Would be allowed</dt>
            <dd style={{ margin: 0 }}>{dryRunResult.would_be_allowed ? "yes" : "no"}</dd>
          </div>
          <div>
            <dt className="metric-label">Notional</dt>
            <dd style={{ margin: 0 }}>{dryRunResult.notional}</dd>
          </div>
          <div>
            <dt className="metric-label">Blocking codes</dt>
            <dd style={{ margin: 0 }}>
              {dryRunResult.blocking_codes.length
                ? dryRunResult.blocking_codes.join(", ")
                : "—"}
            </dd>
          </div>
        </dl>
      ) : null}
    </form>
  );
}
