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
