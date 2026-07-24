"use server";

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/server/api";
import { ApiClientError } from "@/lib/types";

export type ActionResult =
  | { ok: true; message: string; detail?: string }
  | { ok: false; message: string; detail?: string };

function repoRoot(): string {
  // Prefer explicit override when EOC cwd is not apps/eoc
  if (process.env.ARGUS_REPO_ROOT) return process.env.ARGUS_REPO_ROOT;
  return path.resolve(process.cwd(), "..", "..");
}

function controlScript(name: string): string {
  return path.join(repoRoot(), "scripts", "control-center", name);
}

function runPs1(scriptLeaf: string, timeoutMs = 180_000): Promise<ActionResult> {
  const script = controlScript(scriptLeaf);
  if (!fs.existsSync(script)) {
    return Promise.resolve({
      ok: false,
      message: `Script missing: ${scriptLeaf}`,
      detail: "Use Start / Stop on Home.",
    });
  }

  const isWin = process.platform === "win32";
  const cmd = isWin ? "powershell.exe" : "pwsh";
  const args = isWin
    ? ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script]
    : ["-NoProfile", "-File", script];

  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: repoRoot(),
      windowsHide: true,
      env: {
        ...process.env,
        // Keep the Founder dashboard alive while Start/Stop run from the browser.
        ARGUS_KEEP_DASHBOARD: "1",
      },
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill();
      resolve({
        ok: false,
        message: "Command timed out",
        detail: "Try Start or Stop again from Home.",
      });
    }, timeoutMs);

    child.stdout.on("data", (c: Buffer) => {
      stdout += c.toString();
    });
    child.stderr.on("data", (c: Buffer) => {
      stderr += c.toString();
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({
        ok: false,
        message: err.message,
        detail: "Try Start or Stop again from Home.",
      });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const detail = (stdout || stderr).trim().slice(-2000);
      if (code === 0) {
        resolve({ ok: true, message: `${scriptLeaf} completed.`, detail });
      } else {
        resolve({
          ok: false,
          message: `${scriptLeaf} failed (exit ${code ?? "?"}).`,
          detail,
        });
      }
    });
  });
}

export async function startArgusAction(): Promise<ActionResult> {
  const res = await runPs1("start-argus.ps1", 240_000);
  revalidatePath("/today");
  revalidatePath("/control");
  return res.ok
    ? { ok: true, message: "Argus started.", detail: res.detail }
    : res;
}

export async function stopArgusAction(): Promise<ActionResult> {
  const res = await runPs1("stop-argus.ps1", 120_000);
  revalidatePath("/today");
  revalidatePath("/control");
  return res.ok
    ? { ok: true, message: "Argus stopped. Paper data is preserved. You can Start again here.", detail: res.detail }
    : res;
}

export async function restartArgusAction(): Promise<ActionResult> {
  const res = await runPs1("restart-argus.ps1", 300_000);
  revalidatePath("/today");
  revalidatePath("/control");
  return res.ok
    ? { ok: true, message: "Restart requested.", detail: res.detail }
    : res;
}

export async function backupArgusAction(): Promise<ActionResult> {
  const res = await runPs1("backup-argus.ps1", 300_000);
  revalidatePath("/today");
  revalidatePath("/reports");
  return res.ok
    ? { ok: true, message: "Backup completed.", detail: res.detail }
    : { ok: false, message: "Backup failed.", detail: res.detail };
}

export async function refreshStatusAction(): Promise<ActionResult> {
  revalidatePath("/today");
  revalidatePath("/control");
  return { ok: true, message: "Status refreshed." };
}

function isImmutableConflict(err: unknown): boolean {
  if (!(err instanceof ApiClientError)) return false;
  const body = err.body as { detail?: { code?: string } | string } | null;
  if (body && typeof body === "object" && body.detail && typeof body.detail === "object") {
    if (body.detail.code === "report_immutable") return true;
  }
  return err.message.toLowerCase().includes("immutable");
}

export async function endTradingDayAction(): Promise<{
  ok: boolean;
  reportMessage: string;
  backupMessage: string;
  dailyPnl: string | null;
  tradeCount: number | null;
}> {
  let reportMessage = "Report not attempted.";
  let dailyPnl: string | null = null;
  let tradeCount: number | null = null;

  try {
    const report = await apiFetch<{
      report_date: string;
      content?: { daily_pnl?: string | null; trade_count?: number };
    }>("/api/v1/operations/daily-reports/generate", {
      method: "POST",
      body: {},
    });
    reportMessage = `Report ready for ${report.report_date}.`;
    dailyPnl = report.content?.daily_pnl ?? null;
    tradeCount = report.content?.trade_count ?? null;
  } catch (err) {
    if (isImmutableConflict(err)) {
      reportMessage = "A report already exists for this date (kept as-is).";
      try {
        const rows = await apiFetch<
          Array<{ content?: { daily_pnl?: string | null; trade_count?: number } }>
        >("/api/v1/operations/daily-reports", { searchParams: { limit: 1 } });
        dailyPnl = rows[0]?.content?.daily_pnl ?? null;
        tradeCount = rows[0]?.content?.trade_count ?? null;
      } catch {
        /* ignore */
      }
    } else {
      reportMessage =
        err instanceof Error ? err.message : "Could not generate the daily report.";
    }
  }

  const backup = await backupArgusAction();
  revalidatePath("/today");
  revalidatePath("/reports");

  return {
    ok: backup.ok && !reportMessage.startsWith("Could not"),
    reportMessage,
    backupMessage: backup.message,
    dailyPnl,
    tradeCount,
  };
}
