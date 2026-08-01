import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

/**
 * Run a .ps1 with no console window on Windows.
 * Prefers wscript + run-hidden.vbs (window style 0) because powershell.exe
 * -WindowStyle Hidden still flashes from Task Scheduler / some Node spawns.
 */
export function spawnHiddenPs1(opts: {
  repoRoot: string;
  /** Leaf name under scripts/control-center (e.g. start-argus.ps1). */
  scriptLeaf?: string;
  /** Repo-relative path (e.g. scripts/backup/backup-paper.ps1). */
  scriptRel?: string;
  timeoutMs: number;
  env?: Record<string, string>;
  extraArgs?: string[];
}): Promise<{ ok: boolean; detail: string; code: number | null }> {
  const script = opts.scriptRel
    ? path.join(opts.repoRoot, ...opts.scriptRel.split(/[/\\]+/))
    : path.join(
        opts.repoRoot,
        "scripts",
        "control-center",
        opts.scriptLeaf ?? "",
      );
  const vbs = path.join(
    opts.repoRoot,
    "scripts",
    "control-center",
    "run-hidden.vbs",
  );
  const label = opts.scriptLeaf ?? opts.scriptRel ?? "script.ps1";

  if (!opts.scriptLeaf && !opts.scriptRel) {
    return Promise.resolve({
      ok: false,
      detail: "spawnHiddenPs1: scriptLeaf or scriptRel required",
      code: null,
    });
  }

  if (!fs.existsSync(script)) {
    return Promise.resolve({
      ok: false,
      detail: `${label} missing`,
      code: null,
    });
  }

  const isWin = process.platform === "win32";
  const useVbs = isWin && fs.existsSync(vbs);
  const cmd = useVbs ? "wscript.exe" : isWin ? "powershell.exe" : "pwsh";
  const args = useVbs
    ? ["//B", "//nologo", vbs, script, ...(opts.extraArgs ?? [])]
    : isWin
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
          ...(opts.extraArgs ?? []),
        ]
      : ["-NoProfile", "-File", script, ...(opts.extraArgs ?? [])];

  return new Promise((resolve) => {
    const child = spawn(cmd, args, {
      cwd: opts.repoRoot,
      windowsHide: true,
      stdio: useVbs ? "ignore" : ["ignore", "pipe", "pipe"],
      env: { ...process.env, ARGUS_REPO_ROOT: opts.repoRoot, ...opts.env },
    });
    let detail = "";
    const timer = setTimeout(() => {
      child.kill();
      resolve({
        ok: false,
        detail: detail.slice(-2000) || `${label} timed out`,
        code: null,
      });
    }, opts.timeoutMs);

    if (!useVbs) {
      child.stdout?.on("data", (c: Buffer) => {
        detail += c.toString();
      });
      child.stderr?.on("data", (c: Buffer) => {
        detail += c.toString();
      });
    }

    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({ ok: false, detail: err.message, code: null });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (useVbs && !detail) {
        try {
          const logPath = path.join(
            opts.repoRoot,
            "runtime",
            "control-center",
            "keepalive-task.log",
          );
          if (fs.existsSync(logPath)) {
            const raw = fs.readFileSync(logPath, "utf8");
            detail = raw.trim().slice(-4000);
          }
        } catch {
          /* ignore */
        }
      }
      resolve({
        ok: code === 0,
        detail: detail.trim().slice(-4000),
        code,
      });
    });
  });
}
