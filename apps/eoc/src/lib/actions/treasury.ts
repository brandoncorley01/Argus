"use server";

/**
 * Phase 14 — Treasury and Executive Analytics server actions.
 *
 * Every action here operates on SIMULATED / INTERNAL PAPER capital only.
 * There is no action that can execute a real external transfer:
 * `executeExternalTransferAction` always resolves to the backend's 403
 * `external_transfer_execution_forbidden` response.
 */

import type { ActionResult } from "@/lib/actions/auth";
import { apiFetch } from "@/lib/server/api";

export async function createAllocationAction(
  formData: FormData,
): Promise<ActionResult> {
  const pool_id = String(formData.get("pool_id") ?? "").trim();
  const target_type = String(formData.get("target_type") ?? "").trim();
  const target_id = String(formData.get("target_id") ?? "").trim() || null;
  const amount = String(formData.get("amount") ?? "").trim();
  const max_amount = String(formData.get("max_amount") ?? "").trim() || null;
  const notes = String(formData.get("notes") ?? "").trim() || null;
  if (!pool_id || !target_type || !amount) {
    return { ok: false, message: "Pool, target type, and amount are required." };
  }
  try {
    await apiFetch("/api/v1/treasury/allocations", {
      method: "POST",
      body: { pool_id, target_type, target_id, amount, max_amount, notes },
      idempotencyKey: crypto.randomUUID(),
    });
    return { ok: true, message: "Allocation requested (pending Founder approval)." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Allocation request failed.",
    };
  }
}

export async function approveAllocationAction(
  formData: FormData,
): Promise<ActionResult> {
  const id = String(formData.get("allocation_id") ?? "");
  if (!id) return { ok: false, message: "Allocation id is required." };
  try {
    await apiFetch(`/api/v1/treasury/allocations/${id}/approve`, { method: "POST" });
    return { ok: true, message: "Allocation approved." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Approval failed.",
    };
  }
}

export async function rejectAllocationAction(
  formData: FormData,
): Promise<ActionResult> {
  const id = String(formData.get("allocation_id") ?? "");
  const reason = String(formData.get("reason") ?? "").trim();
  if (!id || !reason) {
    return { ok: false, message: "Allocation id and reason are required." };
  }
  try {
    await apiFetch(`/api/v1/treasury/allocations/${id}/reject`, {
      method: "POST",
      body: { reason },
    });
    return { ok: true, message: "Allocation rejected." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Rejection failed.",
    };
  }
}

export async function reserveAllocationAction(
  formData: FormData,
): Promise<ActionResult> {
  const id = String(formData.get("allocation_id") ?? "");
  if (!id) return { ok: false, message: "Allocation id is required." };
  try {
    await apiFetch(`/api/v1/treasury/allocations/${id}/reserve`, { method: "POST" });
    return { ok: true, message: "Allocation reserved (internal ledger only)." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Reservation failed.",
    };
  }
}

export async function releaseAllocationAction(
  formData: FormData,
): Promise<ActionResult> {
  const id = String(formData.get("allocation_id") ?? "");
  if (!id) return { ok: false, message: "Allocation id is required." };
  try {
    await apiFetch(`/api/v1/treasury/allocations/${id}/release`, { method: "POST" });
    return { ok: true, message: "Allocation released." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Release failed.",
    };
  }
}

export async function createExternalTransferAction(
  formData: FormData,
): Promise<ActionResult> {
  const account_id = String(formData.get("account_id") ?? "").trim();
  const direction = String(formData.get("direction") ?? "").trim();
  const amount = String(formData.get("amount") ?? "").trim();
  const currency = String(formData.get("currency") ?? "USD").trim() || "USD";
  const destination_reference = String(
    formData.get("destination_reference") ?? "",
  ).trim();
  if (!account_id || !direction || !amount || !destination_reference) {
    return { ok: false, message: "All external transfer fields are required." };
  }
  try {
    await apiFetch("/api/v1/treasury/external-transfers", {
      method: "POST",
      body: { account_id, direction, amount, currency, destination_reference },
      idempotencyKey: crypto.randomUUID(),
    });
    return {
      ok: true,
      message: "Transfer instruction created as DRAFT. It can never be executed.",
    };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Create transfer instruction failed.",
    };
  }
}

export async function proposeExternalTransferAction(
  formData: FormData,
): Promise<ActionResult> {
  const id = String(formData.get("instruction_id") ?? "");
  if (!id) return { ok: false, message: "Instruction id is required." };
  try {
    await apiFetch(`/api/v1/treasury/external-transfers/${id}/propose`, {
      method: "POST",
    });
    return { ok: true, message: "Instruction proposed (still not executable)." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Propose failed.",
    };
  }
}

export async function cancelExternalTransferAction(
  formData: FormData,
): Promise<ActionResult> {
  const id = String(formData.get("instruction_id") ?? "");
  const reason = String(formData.get("reason") ?? "").trim() || null;
  if (!id) return { ok: false, message: "Instruction id is required." };
  try {
    await apiFetch(`/api/v1/treasury/external-transfers/${id}/cancel`, {
      method: "POST",
      body: { reason },
    });
    return { ok: true, message: "Instruction cancelled." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Cancel failed.",
    };
  }
}

/**
 * Always fails. There is no reachable backend code path that executes a
 * real external transfer — this exists so the UI can demonstrate the
 * deny-by-default boundary rather than to move any money.
 */
export async function executeExternalTransferAction(
  formData: FormData,
): Promise<ActionResult> {
  const id = String(formData.get("instruction_id") ?? "");
  if (!id) return { ok: false, message: "Instruction id is required." };
  try {
    await apiFetch(`/api/v1/treasury/external-transfers/${id}/execute`, {
      method: "POST",
    });
    return { ok: false, message: "Unreachable — execution must always be forbidden." };
  } catch (err) {
    return {
      ok: false,
      message:
        err instanceof Error
          ? err.message
          : "Execution forbidden (external_transfer_execution_forbidden).",
    };
  }
}

export async function generateAttributionSnapshotAction(
  formData: FormData,
): Promise<ActionResult> {
  const scope = String(formData.get("scope") ?? "").trim();
  const scope_ref = String(formData.get("scope_ref") ?? "").trim() || null;
  const environment_class = String(formData.get("environment_class") ?? "").trim();
  if (!scope || !environment_class) {
    return { ok: false, message: "Scope and environment class are required." };
  }
  try {
    await apiFetch("/api/v1/treasury/attribution/generate", {
      method: "POST",
      body: { scope, scope_ref, environment_class },
    });
    return { ok: true, message: "Attribution snapshot generated." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Attribution generation failed.",
    };
  }
}

export async function generateKpisAction(): Promise<ActionResult> {
  try {
    await apiFetch("/api/v1/treasury/kpis/generate", { method: "POST" });
    return { ok: true, message: "Executive KPI snapshots generated." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "KPI generation failed.",
    };
  }
}

export async function createForecastAction(
  formData: FormData,
): Promise<ActionResult> {
  const name = String(formData.get("name") ?? "").trim();
  const scenario_type = String(formData.get("scenario_type") ?? "").trim();
  const inputs_raw = String(formData.get("inputs") ?? "").trim();
  if (!name || !scenario_type || !inputs_raw) {
    return { ok: false, message: "Name, scenario type, and inputs are required." };
  }
  let inputs: unknown;
  try {
    inputs = JSON.parse(inputs_raw);
  } catch {
    return { ok: false, message: "Inputs must be valid JSON." };
  }
  try {
    await apiFetch("/api/v1/treasury/forecasts", {
      method: "POST",
      body: { name, scenario_type, inputs },
    });
    return { ok: true, message: "Deterministic forecast scenario generated." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Forecast generation failed.",
    };
  }
}

export async function generateReportAction(
  formData: FormData,
): Promise<ActionResult> {
  const report_type = String(formData.get("report_type") ?? "").trim();
  if (!report_type) return { ok: false, message: "Report type is required." };
  try {
    await apiFetch("/api/v1/treasury/reports/generate", {
      method: "POST",
      body: { report_type },
    });
    return { ok: true, message: "Institutional report generated (immutable, hashed)." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Report generation failed.",
    };
  }
}
