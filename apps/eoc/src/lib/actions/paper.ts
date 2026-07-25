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
    revalidatePath("/paper-training");
    revalidatePath("/trades");
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

export async function clearSymbolPracticeAction(input: {
  portfolioId: string;
  symbol: string;
}): Promise<PaperActionResult> {
  try {
    const result = await apiFetch<{ message: string }>(
      `/api/v1/paper/portfolios/${input.portfolioId}/symbols/${encodeURIComponent(input.symbol)}/clear-practice`,
      { method: "POST", requireCsrf: true },
    );
    revalidatePath("/today");
    revalidatePath("/trades");
    revalidatePath("/paper-training");
    return {
      ok: true,
      message:
        result.message ||
        `Cleared paper practice for ${input.symbol}. Refresh recent prices next.`,
    };
  } catch (err) {
    const message =
      err instanceof ApiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Could not clear that paper trade.";
    return { ok: false, message };
  }
}

export async function refreshRecentPricesAction(): Promise<PaperActionResult> {
  try {
    const result = await apiFetch<{
      ok: boolean;
      next_step: string;
      records_accepted: number;
    }>("/api/v1/market/prices/refresh", {
      method: "POST",
      requireCsrf: true,
    });
    revalidatePath("/today");
    revalidatePath("/paper-training");
    revalidatePath("/market");
    return {
      ok: result.ok,
      message:
        result.next_step ||
        `Saved ${result.records_accepted} recent price updates.`,
    };
  } catch (err) {
    const message =
      err instanceof ApiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Could not refresh recent prices.";
    return { ok: false, message };
  }
}

export async function setTrainingModeAction(input: {
  portfolioId: string;
  mode: "automatic" | "coaching";
  defaultNotional?: string;
}): Promise<PaperActionResult> {
  try {
    await apiFetch(`/api/v1/paper/training/${input.portfolioId}/settings`, {
      method: "PUT",
      body: {
        mode: input.mode,
        default_notional: input.defaultNotional ?? null,
      },
      requireCsrf: true,
    });
    revalidatePath("/paper-training");
    revalidatePath("/today");
    return {
      ok: true,
      message:
        input.mode === "automatic"
          ? "Automatic Practice is on. Argus may open simulated trades on its own."
          : "Coaching Mode is on. Argus will wait for your Take or Skip before entering.",
    };
  } catch (err) {
    const message =
      err instanceof ApiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Could not update training mode.";
    return { ok: false, message };
  }
}

export async function coachingTakeAction(input: {
  portfolioId: string;
  candidateId: string;
  note?: string;
}): Promise<PaperActionResult> {
  try {
    const result = await apiFetch<{ message: string }>(
      `/api/v1/paper/training/${input.portfolioId}/coaching/take`,
      {
        method: "POST",
        body: { candidate_id: input.candidateId, note: input.note ?? null },
        requireCsrf: true,
      },
    );
    revalidatePath("/paper-training");
    revalidatePath("/today");
    revalidatePath("/trades");
    return { ok: true, message: result.message };
  } catch (err) {
    const message =
      err instanceof ApiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Could not take this paper trade.";
    return { ok: false, message };
  }
}

export async function coachingSkipAction(input: {
  portfolioId: string;
  candidateId: string;
  note?: string;
}): Promise<PaperActionResult> {
  try {
    const result = await apiFetch<{ message: string }>(
      `/api/v1/paper/training/${input.portfolioId}/coaching/skip`,
      {
        method: "POST",
        body: { candidate_id: input.candidateId, note: input.note ?? null },
        requireCsrf: true,
      },
    );
    revalidatePath("/paper-training");
    revalidatePath("/today");
    return { ok: true, message: result.message };
  } catch (err) {
    const message =
      err instanceof ApiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Could not skip this idea.";
    return { ok: false, message };
  }
}

export async function recordTrainingFeedbackAction(input: {
  portfolioId: string;
  feedbackCode: string;
  symbol: string;
  fillId?: string;
  candidateId?: string;
  note?: string;
}): Promise<PaperActionResult> {
  try {
    await apiFetch(`/api/v1/paper/training/${input.portfolioId}/feedback`, {
      method: "POST",
      body: {
        feedback_code: input.feedbackCode,
        symbol: input.symbol,
        fill_id: input.fillId ?? null,
        candidate_id: input.candidateId ?? null,
        note: input.note ?? null,
      },
      requireCsrf: true,
    });
    revalidatePath("/paper-training");
    revalidatePath("/today");
    return {
      ok: true,
      message:
        "Feedback saved for paper review only. It does not change live trading rules.",
    };
  } catch (err) {
    const message =
      err instanceof ApiClientError
        ? err.message
        : err instanceof Error
          ? err.message
          : "Could not save feedback.";
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
    revalidatePath("/paper-training");
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
