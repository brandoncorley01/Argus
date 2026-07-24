"use server";

/**
 * Phase 13 — Micro-Live Institution server actions.
 *
 * These actions proxy to the deny-by-default micro-live API. None of them
 * can activate real live trading: the backend has no reachable code path
 * to MICRO_LIVE_ACTIVE, credential endpoints never accept or return
 * secret values (reference names only), and dry-run validation never
 * submits an order.
 */

import type { ActionResult } from "@/lib/actions/auth";
import { apiFetch } from "@/lib/server/api";
import type { DryRunOrderResult } from "@/lib/types";

export async function transitionActivationAction(
  formData: FormData,
): Promise<ActionResult> {
  const target_state = String(formData.get("target_state") ?? "").trim();
  const reason = String(formData.get("reason") ?? "").trim();
  if (!target_state || !reason) {
    return { ok: false, message: "Target state and reason are required." };
  }
  try {
    await apiFetch("/api/v1/micro-live/activation/transition", {
      method: "POST",
      body: { target_state, reason },
      idempotencyKey: crypto.randomUUID(),
    });
    return { ok: true, message: `Transition to ${target_state} submitted.` };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Transition failed.",
    };
  }
}

export async function createCredentialReferenceAction(
  formData: FormData,
): Promise<ActionResult> {
  const provider_key = String(formData.get("provider_key") ?? "").trim();
  const ref_name = String(formData.get("ref_name") ?? "").trim();
  const purpose = String(formData.get("purpose") ?? "").trim();
  if (!provider_key || !ref_name || !purpose) {
    return {
      ok: false,
      message: "Provider, reference name, and purpose are required.",
    };
  }
  try {
    await apiFetch("/api/v1/micro-live/credential-references", {
      method: "POST",
      body: { provider_key, ref_name, purpose },
    });
    return {
      ok: true,
      message: `Credential reference ${ref_name} registered (presence-only; no value stored).`,
    };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Create reference failed.",
    };
  }
}

export async function validateCredentialReferenceAction(
  formData: FormData,
): Promise<ActionResult> {
  const id = String(formData.get("reference_id") ?? "");
  if (!id) return { ok: false, message: "Reference id is required." };
  try {
    await apiFetch(`/api/v1/micro-live/credential-references/${id}/validate`, {
      method: "POST",
    });
    return { ok: true, message: "Presence check completed (no value exposed)." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Validation failed.",
    };
  }
}

export async function setKillSwitchAction(
  formData: FormData,
): Promise<ActionResult> {
  const scope_type = String(formData.get("scope_type") ?? "").trim();
  const scope_id = String(formData.get("scope_id") ?? "").trim() || null;
  const active = formData.get("active") === "on";
  const reason = String(formData.get("reason") ?? "").trim() || null;
  if (!scope_type) return { ok: false, message: "Scope type is required." };
  try {
    await apiFetch("/api/v1/micro-live/kill-switches", {
      method: "POST",
      body: { scope_type, scope_id, active, reason },
      idempotencyKey: crypto.randomUUID(),
    });
    return {
      ok: true,
      message: `Kill switch (${scope_type}) set to ${active ? "ACTIVE" : "cleared"}.`,
    };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Kill switch update failed.",
    };
  }
}

export async function putCapitalPolicyAction(
  formData: FormData,
): Promise<ActionResult> {
  const fields = [
    "max_deployable_capital",
    "max_order_notional",
    "max_daily_loss",
    "max_concurrent_exposure",
    "max_provider_exposure",
    "max_strategy_exposure",
  ] as const;
  const body: Record<string, string> = {};
  for (const f of fields) {
    const v = String(formData.get(f) ?? "").trim();
    if (!v) return { ok: false, message: `${f} is required.` };
    body[f] = v;
  }
  try {
    await apiFetch("/api/v1/micro-live/capital-policy", {
      method: "PUT",
      body,
    });
    return { ok: true, message: "Micro-capital policy updated." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Policy update failed.",
    };
  }
}

export async function createReconciliationRunAction(
  formData: FormData,
): Promise<ActionResult> {
  const provider_key = String(formData.get("provider_key") ?? "").trim();
  const authoritative_raw = String(formData.get("authoritative_state") ?? "");
  const comparison_raw = String(formData.get("comparison_state") ?? "");
  if (!provider_key || !authoritative_raw || !comparison_raw) {
    return {
      ok: false,
      message: "Provider and both fixture states are required.",
    };
  }
  let authoritative_state: unknown;
  let comparison_state: unknown;
  try {
    authoritative_state = JSON.parse(authoritative_raw);
    comparison_state = JSON.parse(comparison_raw);
  } catch {
    return { ok: false, message: "Fixture states must be valid JSON." };
  }
  try {
    await apiFetch("/api/v1/micro-live/reconciliation/runs", {
      method: "POST",
      body: { provider_key, authoritative_state, comparison_state },
    });
    return { ok: true, message: "Reconciliation run completed." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Reconciliation run failed.",
    };
  }
}

export async function dryRunValidateOrderAction(
  formData: FormData,
): Promise<ActionResult & { result?: DryRunOrderResult }> {
  const quantity = String(formData.get("quantity") ?? "").trim();
  const reference_price = String(formData.get("reference_price") ?? "").trim();
  if (!quantity || !reference_price) {
    return { ok: false, message: "Quantity and reference price are required." };
  }
  try {
    const result = await apiFetch<DryRunOrderResult>(
      "/api/v1/micro-live/dry-run/validate-order",
      { method: "POST", body: { quantity, reference_price } },
    );
    return {
      ok: true,
      message: result.would_be_allowed
        ? "Dry-run: would be allowed under current policy (no order submitted)."
        : `Dry-run: would be BLOCKED — ${result.blocking_codes.join(", ")}`,
      result,
    };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Dry-run validation failed.",
    };
  }
}
