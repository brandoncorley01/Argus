"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/server/api";
import { ApiClientError } from "@/lib/types";

export type PaperActionResult =
  | { ok: true; message: string }
  | { ok: false; message: string };

export async function pauseNewEntriesAction(
  portfolioId: string,
  active: boolean,
): Promise<PaperActionResult> {
  try {
    await apiFetch(`/api/v1/paper/portfolios/${portfolioId}/pause-new-entries`, {
      method: "POST",
      body: { active },
      requireCsrf: true,
    });
    revalidatePath("/today");
    revalidatePath("/trading");
    return {
      ok: true,
      message: active
        ? "New paper entries paused. Open positions can still be managed."
        : "New paper entries resumed.",
    };
  } catch (err) {
    const message =
      err instanceof ApiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Could not update pause setting.";
    return { ok: false, message };
  }
}

export async function runMarketScanAction(
  force = true,
): Promise<PaperActionResult> {
  try {
    await apiFetch("/api/v1/market/scan/run", {
      method: "POST",
      searchParams: { force: force ? "true" : "false" },
      requireCsrf: true,
    });
    revalidatePath("/today");
    return { ok: true, message: "Scan finished. Home will refresh with the latest look." };
  } catch (err) {
    const message =
      err instanceof ApiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Could not run market scan.";
    return { ok: false, message };
  }
}

export async function teachScanAction(input: {
  symbol: string;
  signal: "interested" | "not_interested" | "needs_more_data" | "looks_wrong";
  candidateId?: string | null;
  note?: string;
}): Promise<PaperActionResult> {
  try {
    await apiFetch("/api/v1/market/scan/teach", {
      method: "POST",
      body: {
        symbol: input.symbol,
        signal: input.signal,
        candidate_id: input.candidateId ?? null,
        note: input.note ?? null,
      },
      requireCsrf: true,
    });
    revalidatePath("/today");
    return {
      ok: true,
      message: "Teaching note saved. No paper order was placed.",
    };
  } catch (err) {
    const message =
      err instanceof ApiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Could not save teaching note.";
    return { ok: false, message };
  }
}
