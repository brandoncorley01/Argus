"use server";

import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

import { revalidatePath } from "next/cache";

import { apiFetch } from "@/lib/server/api";
import { apiBaseUrl } from "@/lib/server/env";
import { ApiClientError } from "@/lib/types";

export type ActionResult =
  | { ok: true; message: string; detail?: string }
  | { ok: false; message: string; detail?: string };

function repoRoot(): string {
  if (process.env.ARGUS_REPO_ROOT) {
    const envRoot = process.env.ARGUS_REPO_ROOT;
    if (
      fs.existsSync(path.join(envRoot, "docker-compose.yml")) &&
      fs.existsSync(path.join(envRoot, "scripts", "control-center"))
    ) {
      return envRoot;
    }
  }
  let cur = path.resolve(process.cwd());
  for (let i = 0; i < 6; i++) {
    if (
      fs.existsSync(path.join(cur, "docker-compose.yml")) &&
      fs.existsSync(path.join(cur, "scripts", "control-center"))
    ) {
      return cur;
    }
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  return path.resolve(process.cwd(), "..", "..");
}

function controlScript(name: string): string {
  return path.join(repoRoot(), "scripts", "control-center", name);
}

function runCommand(
  cmd: string,
  args: string[],
  timeoutMs: number,
  env?: Record<string, string>,
): Promise<ActionResult> {
  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: repoRoot(),
      windowsHide: true,
      env: { ...process.env, ...env },
    });
    let stdout = "";
    let stderr = "";
    const timer = setTimeout(() => {
      child.kill();
      resolve({
        ok: false,
        message: "Command timed out",
        detail: "Try Start again from Home.",
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
        detail: "Try Start again from Home.",
      });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      const detail = (stdout || stderr).trim().slice(-4000);
      if (code === 0) {
        resolve({ ok: true, message: "ok", detail });
      } else {
        resolve({
          ok: false,
          message: `Command failed (exit ${code ?? "?"}).`,
          detail,
        });
      }
    });
  });
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
    ? [
        "-NoProfile",
        "-NoLogo",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        script,
      ]
    : ["-NoProfile", "-File", script];

  return runCommand(cmd, args, timeoutMs, { ARGUS_KEEP_DASHBOARD: "1" });
}

export async function startArgusAction(): Promise<ActionResult> {
  // If already up, do not re-run Start (keeps the "car running" model).
  try {
    const ready = await fetch(`${apiBaseUrl()}/ready`, {
      cache: "no-store",
      signal: AbortSignal.timeout(4_000),
    });
    if (ready.ok) {
      revalidatePath("/today");
      revalidatePath("/control");
      return {
        ok: true,
        message: "Argus is already Running. It stays up until you press Stop.",
      };
    }
  } catch {
    // Fall through to start script.
  }

  // Single sync path: start-argus.ps1 self-updates from GitHub then force-syncs
  // main. Do not wipe apps/eoc/.next or kill :3000 here — that aborts this
  // server action and leaves Home stuck on Starting…
  const res = await runPs1("start-argus.ps1", 240_000);
  revalidatePath("/today");
  revalidatePath("/control");
  if (!res.ok) {
    return {
      ok: false,
      message: res.message,
      detail: res.detail,
    };
  }
  return {
    ok: true,
    message: "Argus started. It will keep Running until you press Stop.",
    detail: res.detail,
  };
}

export async function stopArgusAction(): Promise<ActionResult> {
  const res = await runPs1("stop-argus.ps1", 120_000);
  revalidatePath("/today");
  revalidatePath("/control");
  return res.ok
    ? {
        ok: true,
        message: "Argus stopped. Paper data is preserved. You can Start again here.",
        detail: res.detail,
      }
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
