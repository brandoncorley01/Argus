"use server";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/server/api";
import { ApiClientError } from "@/lib/types";

export type ActionResult =
  | { ok: true; message?: string }
  | { ok: false; message: string };

export async function generateDailyReportAction(
  formData: FormData,
): Promise<ActionResult> {
  const raw = String(formData.get("report_date") ?? "").trim();
  const body: { report_date?: string } = {};
  if (raw) body.report_date = raw;

  try {
    const report = await apiFetch<{ report_date: string; content_hash: string }>(
      "/api/v1/operations/daily-reports/generate",
      {
        method: "POST",
        body,
      },
    );
    revalidatePath("/overview");
    revalidatePath("/system-health");
    return {
      ok: true,
      message: `Daily paper report generated for ${report.report_date}.`,
    };
  } catch (err) {
    if (err instanceof ApiClientError) {
      return { ok: false, message: err.message };
    }
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Generate daily report failed.",
    };
  }
}
