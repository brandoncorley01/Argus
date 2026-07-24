"use client";

import { useState, useTransition } from "react";

import {
  approveAllocationAction,
  cancelExternalTransferAction,
  createAllocationAction,
  createExternalTransferAction,
  createForecastAction,
  executeExternalTransferAction,
  generateAttributionSnapshotAction,
  generateKpisAction,
  generateReportAction,
  proposeExternalTransferAction,
  rejectAllocationAction,
  releaseAllocationAction,
  reserveAllocationAction,
} from "@/lib/actions/treasury";
import type { ActionResult } from "@/lib/actions/auth";
import type { CapitalPool, TreasuryAccount } from "@/lib/types";

function ResultBanner({ result }: { result: ActionResult | null }) {
  if (!result) return null;
  return (
    <div className={`alert ${result.ok ? "ok" : "error"}`} role="status">
      {result.message}
    </div>
  );
}

export function AllocationRequestForm({ pools }: { pools: CapitalPool[] }) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await createAllocationAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
        Requests a capital allocation from a simulated pool. Requires Founder
        approval before it can be reserved.
      </p>
      <div className="field">
        <label htmlFor="pool_id">Pool</label>
        <select id="pool_id" name="pool_id" required disabled={pending}>
          <option value="">Select pool</option>
          {pools.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} ({p.pool_type})
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="target_type">Target type</label>
        <select id="target_type" name="target_type" required disabled={pending}>
          <option value="strategy">strategy</option>
          <option value="portfolio">portfolio</option>
          <option value="provider">provider</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="target_id">Target id (optional)</label>
        <input id="target_id" name="target_id" disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="amount">Amount</label>
        <input
          id="amount"
          name="amount"
          type="text"
          inputMode="decimal"
          required
          disabled={pending}
        />
      </div>
      <div className="field">
        <label htmlFor="max_amount">Max amount (optional)</label>
        <input id="max_amount" name="max_amount" type="text" inputMode="decimal" disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="notes">Notes</label>
        <textarea id="notes" name="notes" rows={2} disabled={pending} />
      </div>
      <button className="btn" type="submit" disabled={pending}>
        {pending ? "Requesting…" : "Request allocation"}
      </button>
    </form>
  );
}

export function AllocationActions({
  allocationId,
  status,
  canApprove,
}: {
  allocationId: string;
  status: string;
  canApprove: boolean;
}) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  function run(action: (fd: FormData) => Promise<ActionResult>, extra?: Record<string, string>) {
    const fd = new FormData();
    fd.set("allocation_id", allocationId);
    if (extra) for (const [k, v] of Object.entries(extra)) fd.set(k, v);
    startTransition(async () => {
      const res = await action(fd);
      setResult(res);
      if (res.ok) window.location.reload();
    });
  }

  if (!canApprove) return null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
      {result ? (
        <span style={{ fontSize: "0.75rem" }} className={result.ok ? "" : "error"}>
          {result.message}
        </span>
      ) : null}
      <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
        {status === "requested" ? (
          <>
            <button
              className="btn secondary"
              disabled={pending}
              onClick={() => run(approveAllocationAction)}
            >
              Approve
            </button>
            <button
              className="btn danger"
              disabled={pending}
              onClick={() => {
                const reason = window.prompt("Rejection reason:");
                if (reason) run(rejectAllocationAction, { reason });
              }}
            >
              Reject
            </button>
          </>
        ) : null}
        {status === "approved" ? (
          <button
            className="btn secondary"
            disabled={pending}
            onClick={() => run(reserveAllocationAction)}
          >
            Reserve
          </button>
        ) : null}
        {status === "active" ? (
          <button
            className="btn secondary"
            disabled={pending}
            onClick={() => run(releaseAllocationAction)}
          >
            Release
          </button>
        ) : null}
      </div>
    </div>
  );
}

export function ExternalTransferCreateForm({ accounts }: { accounts: TreasuryAccount[] }) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await createExternalTransferAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
        Creates a DRAFT instruction only. No instruction created here can ever
        reach an executed state — the backend refuses execution
        unconditionally.
      </p>
      <div className="field">
        <label htmlFor="account_id">Account</label>
        <select id="account_id" name="account_id" required disabled={pending}>
          <option value="">Select account</option>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="direction">Direction</label>
        <select id="direction" name="direction" required disabled={pending}>
          <option value="inbound">inbound</option>
          <option value="outbound">outbound</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="amount">Amount</label>
        <input id="amount" name="amount" type="text" inputMode="decimal" required disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="currency">Currency</label>
        <input id="currency" name="currency" defaultValue="USD" disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="destination_reference">Destination reference</label>
        <input
          id="destination_reference"
          name="destination_reference"
          placeholder="Descriptive reference only — not a real account number"
          required
          disabled={pending}
        />
      </div>
      <button className="btn" type="submit" disabled={pending}>
        {pending ? "Creating…" : "Create draft instruction"}
      </button>
    </form>
  );
}

export function ExternalTransferActions({
  instructionId,
  status,
}: {
  instructionId: string;
  status: string;
}) {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  function run(action: (fd: FormData) => Promise<ActionResult>, extra?: Record<string, string>) {
    const fd = new FormData();
    fd.set("instruction_id", instructionId);
    if (extra) for (const [k, v] of Object.entries(extra)) fd.set(k, v);
    startTransition(async () => {
      const res = await action(fd);
      setResult(res);
      if (res.ok) window.location.reload();
    });
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "0.35rem" }}>
      {result ? (
        <span style={{ fontSize: "0.75rem" }} className={result.ok ? "" : "error"}>
          {result.message}
        </span>
      ) : null}
      <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
        {status === "draft" ? (
          <button
            className="btn secondary"
            disabled={pending}
            onClick={() => run(proposeExternalTransferAction)}
          >
            Propose
          </button>
        ) : null}
        {status === "draft" || status === "proposed" ? (
          <button
            className="btn secondary"
            disabled={pending}
            onClick={() => run(cancelExternalTransferAction)}
          >
            Cancel
          </button>
        ) : null}
        <button
          className="btn danger"
          disabled={pending}
          onClick={() => {
            if (
              !window.confirm(
                "This will attempt execution and is expected to be refused (403 forbidden). Continue?",
              )
            ) {
              return;
            }
            run(executeExternalTransferAction);
          }}
        >
          Attempt execute (always forbidden)
        </button>
      </div>
    </div>
  );
}

export function AttributionGenerateForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await generateAttributionSnapshotAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      <div className="field">
        <label htmlFor="scope">Scope</label>
        <select id="scope" name="scope" required disabled={pending}>
          <option value="strategy">strategy</option>
          <option value="portfolio">portfolio</option>
          <option value="instrument">instrument</option>
          <option value="provider">provider</option>
          <option value="fee">fee</option>
          <option value="slippage">slippage</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="scope_ref">Scope reference (optional, e.g. portfolio id)</label>
        <input id="scope_ref" name="scope_ref" disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="environment_class">Environment class</label>
        <select id="environment_class" name="environment_class" required disabled={pending}>
          <option value="paper">paper</option>
          <option value="simulated">simulated</option>
          <option value="sandbox">sandbox</option>
          <option value="testnet">testnet</option>
          <option value="live">live (always unavailable in this system)</option>
        </select>
      </div>
      <button className="btn" type="submit" disabled={pending}>
        {pending ? "Generating…" : "Generate attribution snapshot"}
      </button>
    </form>
  );
}

export function KpiGenerateButton() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <div>
      <ResultBanner result={result} />
      <button
        className="btn"
        disabled={pending}
        onClick={() =>
          startTransition(async () => {
            const res = await generateKpisAction();
            setResult(res);
            if (res.ok) window.location.reload();
          })
        }
      >
        {pending ? "Generating…" : "Generate KPI snapshots"}
      </button>
    </div>
  );
}

export function ForecastForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await createForecastAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>
        Deterministic projection from the inputs you supply only — never a
        market prediction.
      </p>
      <div className="field">
        <label htmlFor="name">Scenario name</label>
        <input id="name" name="name" required disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="scenario_type">Scenario type</label>
        <select id="scenario_type" name="scenario_type" required disabled={pending}>
          <option value="cash_flow">cash_flow</option>
          <option value="capital_requirement">capital_requirement</option>
          <option value="drawdown">drawdown</option>
          <option value="provider_outage">provider_outage</option>
          <option value="strategy_suspension">strategy_suspension</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="inputs">Inputs — JSON</label>
        <textarea id="inputs" name="inputs" rows={3} required disabled={pending} />
      </div>
      <button className="btn secondary" type="submit" disabled={pending}>
        {pending ? "Computing…" : "Generate forecast"}
      </button>
    </form>
  );
}

export function ReportGenerateForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await generateReportAction(new FormData(form));
          setResult(res);
          if (res.ok) window.location.reload();
        });
      }}
    >
      <ResultBanner result={result} />
      <div className="field">
        <label htmlFor="report_type">Report type</label>
        <select id="report_type" name="report_type" required disabled={pending}>
          <option value="daily_brief">daily_brief</option>
          <option value="weekly_executive">weekly_executive</option>
          <option value="monthly_performance">monthly_performance</option>
          <option value="quarterly_review">quarterly_review</option>
        </select>
      </div>
      <button className="btn" type="submit" disabled={pending}>
        {pending ? "Generating…" : "Generate report (new immutable version)"}
      </button>
    </form>
  );
}
