"use server";

import path from "node:path";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/server/api";
import { spawnHiddenPs1 } from "@/lib/server/spawnHiddenPs1";
import { ApiClientError } from "@/lib/types";

export type ActionResult =
  | { ok: true; message?: string; code?: string }
  | { ok: false; message: string; code?: string };

export type EndTradingDayResult = {
  ok: boolean;
  report: { status: "generated" | "already_exists" | "failed"; message: string; reportDate?: string };
  backup: { status: "ok" | "failed" | "skipped"; message: string };
  summary: {
    dailyPnl: string | null;
    tradeCount: number | null;
    openPositions: number | null;
  };
};

function isImmutableConflict(err: unknown): boolean {
  if (!(err instanceof ApiClientError)) return false;
  const body = err.body as { detail?: { code?: string; message?: string } | string } | null;
  if (body && typeof body === "object" && body.detail && typeof body.detail === "object") {
    if (body.detail.code === "report_immutable") return true;
  }
  const msg = err.message.toLowerCase();
  return msg.includes("immutable") || msg.includes("already exists");
}

function repoRoot(): string {
  // apps/eoc -> repo root
  return path.resolve(process.cwd(), "..", "..");
}

async function runBackupScript(): Promise<{ ok: boolean; message: string }> {
  const root = repoRoot();
  const res = await spawnHiddenPs1({
    repoRoot: root,
    scriptRel: "scripts/backup/backup-paper.ps1",
    timeoutMs: 180_000,
  });
  if (res.ok) {
    return { ok: true, message: "Backup completed and verified." };
  }
  return {
    ok: false,
    message: res.detail.trim() || `Backup failed (exit ${res.code ?? "unknown"}).`,
  };
}

export async function generateDailyReportFounderAction(
  formData: FormData,
): Promise<ActionResult> {
  const raw = String(formData.get("report_date") ?? "").trim();
  const body: { report_date?: string } = {};
  if (raw) body.report_date = raw;

  try {
    const report = await apiFetch<{ report_date: string }>(
      "/api/v1/operations/daily-reports/generate",
      { method: "POST", body },
    );
    revalidatePath("/today");
    revalidatePath("/reports");
    revalidatePath("/overview");
    revalidatePath("/system-health");
    return {
      ok: true,
      message: `Daily paper report generated for ${report.report_date}.`,
      code: "generated",
    };
  } catch (err) {
    if (isImmutableConflict(err)) {
      return {
        ok: true,
        message: "A report already exists for this date.",
        code: "already_exists",
      };
    }
    if (err instanceof ApiClientError) {
      return { ok: false, message: err.message };
    }
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Could not generate the daily report.",
    };
  }
}

export async function resumePaperTradingAction(
  portfolioId: string,
): Promise<ActionResult> {
  try {
    await apiFetch(`/api/v1/paper/portfolios/${portfolioId}/kill-switch`, {
      method: "POST",
      body: { active: false },
    });
    revalidatePath("/today");
    revalidatePath("/trading");
    revalidatePath("/portfolio");
    return { ok: true, message: "Paper trading resumed." };
  } catch (err) {
    if (err instanceof ApiClientError) {
      return { ok: false, message: err.message };
    }
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Could not resume paper trading.",
    };
  }
}

export async function endTradingDayAction(): Promise<EndTradingDayResult> {
  let reportStatus: EndTradingDayResult["report"] = {
    status: "failed",
    message: "Report not attempted.",
  };
  let dailyPnl: string | null = null;
  let tradeCount: number | null = null;
  let openPositions: number | null = null;

  try {
    const report = await apiFetch<{
      report_date: string;
      content?: {
        daily_pnl?: string | null;
        trade_count?: number;
        open_positions?: unknown[];
      };
    }>("/api/v1/operations/daily-reports/generate", {
      method: "POST",
      body: {},
    });
    reportStatus = {
      status: "generated",
      message: `Report generated for ${report.report_date}.`,
      reportDate: report.report_date,
    };
    dailyPnl = report.content?.daily_pnl ?? null;
    tradeCount = report.content?.trade_count ?? null;
    openPositions = report.content?.open_positions?.length ?? null;
  } catch (err) {
    if (isImmutableConflict(err)) {
      reportStatus = {
        status: "already_exists",
        message: "A report already exists for this date. The existing report was preserved.",
      };
      try {
        const existing = await apiFetch<
          Array<{
            report_date: string;
            content?: {
              daily_pnl?: string | null;
              trade_count?: number;
              open_positions?: unknown[];
            };
          }>
        >("/api/v1/operations/daily-reports", { searchParams: { limit: 1 } });
        const latest = existing[0];
        if (latest) {
          reportStatus.reportDate = latest.report_date;
          dailyPnl = latest.content?.daily_pnl ?? null;
          tradeCount = latest.content?.trade_count ?? null;
          openPositions = latest.content?.open_positions?.length ?? null;
        }
      } catch {
        // keep preserved message
      }
    } else {
      reportStatus = {
        status: "failed",
        message:
          err instanceof Error ? err.message : "Daily report could not be generated.",
      };
    }
  }

  const backup = await runBackupScript();

  revalidatePath("/today");
  revalidatePath("/reports");
  revalidatePath("/end-day");
  revalidatePath("/overview");
  revalidatePath("/system-health");

  const ok =
    (reportStatus.status === "generated" || reportStatus.status === "already_exists") &&
    backup.ok;

  return {
    ok,
    report: reportStatus,
    backup: {
      status: backup.ok ? "ok" : "failed",
      message: backup.message,
    },
    summary: {
      dailyPnl,
      tradeCount,
      openPositions,
    },
  };
}
