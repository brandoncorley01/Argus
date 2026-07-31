import { spawn } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";

import { apiBaseUrl } from "@/lib/server/env";

export type ReachabilityReport = {
  desired_running: boolean;
  docker_engine: boolean;
  postgres: boolean;
  redis: boolean;
  api_health: boolean;
  api_ready: boolean;
  blocking: "none" | "stopped" | "docker" | "postgres" | "redis" | "api";
  message: string;
  recovering?: boolean;
};

function looksLikeRepoRoot(dir: string): boolean {
  return (
    fs.existsSync(path.join(dir, "docker-compose.yml")) &&
    fs.existsSync(path.join(dir, "scripts", "control-center"))
  );
}

function repoRoot(): string {
  if (process.env.ARGUS_REPO_ROOT && looksLikeRepoRoot(process.env.ARGUS_REPO_ROOT)) {
    return process.env.ARGUS_REPO_ROOT;
  }
  // Walk up from cwd — Next may run with cwd=apps/eoc or monorepo root.
  let cur = path.resolve(process.cwd());
  for (let i = 0; i < 6; i++) {
    if (looksLikeRepoRoot(cur)) return cur;
    const parent = path.dirname(cur);
    if (parent === cur) break;
    cur = parent;
  }
  // Last resort: historical apps/eoc -> ../..
  return path.resolve(process.cwd(), "..", "..");
}

function desiredStatePath(): string {
  return path.join(repoRoot(), "runtime", "control-center", "desired-state.json");
}

export function readDesiredRunning(): boolean {
  try {
    // PowerShell Set-Content -Encoding utf8 writes a BOM; JSON.parse rejects it.
    const raw = fs.readFileSync(desiredStatePath(), "utf8").replace(/^\uFEFF/, "");
    const obj = JSON.parse(raw) as { running?: unknown };
    return Boolean(obj.running);
  } catch {
    return false;
  }
}

function probeTcp(host: string, port: number, timeoutMs = 1500): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.connect({ host, port });
    const done = (ok: boolean) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(ok);
    };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
  });
}

async function probeHttp(url: string, timeoutMs = 3000): Promise<boolean> {
  try {
    const res = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.timeout(timeoutMs),
    });
    return res.ok;
  } catch {
    return false;
  }
}

function probeDockerEngine(): Promise<boolean> {
  const dockerBins = [
    "docker",
    path.join(
      process.env.ProgramFiles || "C:\\Program Files",
      "Docker",
      "Docker",
      "resources",
      "bin",
      "docker.exe",
    ),
  ];
  return new Promise((resolve) => {
    let index = 0;
    const tryNext = () => {
      if (index >= dockerBins.length) {
        resolve(false);
        return;
      }
      const bin = dockerBins[index++];
      // `docker version` is faster than `docker info` on Desktop cold starts.
      const child = spawn(bin, ["version", "--format", "{{.Server.Version}}"], {
        windowsHide: true,
        stdio: ["ignore", "pipe", "ignore"],
        env: process.env,
      });
      let out = "";
      const timer = setTimeout(() => {
        child.kill();
        tryNext();
      }, 8_000);
      child.stdout?.on("data", (c: Buffer) => {
        out += c.toString();
      });
      child.on("error", () => {
        clearTimeout(timer);
        tryNext();
      });
      child.on("close", (code) => {
        clearTimeout(timer);
        if (code === 0 && out.trim().length > 0) resolve(true);
        else tryNext();
      });
    };
    tryNext();
  });
}

export async function probeReachability(): Promise<ReachabilityReport> {
  const desired_running = readDesiredRunning();
  const [docker_engine, postgres, redis, api_health, api_ready] = await Promise.all([
    probeDockerEngine(),
    probeTcp("127.0.0.1", Number(process.env.POSTGRES_PORT || 5432)),
    probeTcp("127.0.0.1", Number(process.env.REDIS_PORT || 6379)),
    probeHttp(`${apiBaseUrl()}/health`),
    probeHttp(`${apiBaseUrl()}/ready`),
  ]);

  // If postgres/redis answer on loopback, the engine is effectively up even when
  // `docker version` is slow/unavailable from the Node PATH.
  const dockerOk = docker_engine || (postgres && redis);

  let blocking: ReachabilityReport["blocking"] = "none";
  let message = "Argus API is reachable.";

  if (api_ready && api_health) {
    blocking = "none";
    message = desired_running
      ? "Argus is Running."
      : "Argus API is up (desired state is Stopped).";
  } else if (!desired_running) {
    blocking = "stopped";
    message =
      "Argus is Stopped. Press Start Argus on this page (or the desktop shortcut), wait until Ready, then sign in.";
  } else if (!dockerOk) {
    blocking = "docker";
    message =
      "Docker Desktop is not ready. Opening recovery — if prompted, finish Docker sign-in, then wait.";
  } else if (!postgres) {
    blocking = "postgres";
    message = "Postgres is down. Recovering Docker infrastructure…";
  } else if (!redis) {
    blocking = "redis";
    message = "Redis is down. Recovering Docker infrastructure…";
  } else {
    blocking = "api";
    message = "Argus API is down while desired state is Running. Recovering…";
  }

  return {
    desired_running,
    docker_engine: dockerOk,
    postgres,
    redis,
    api_health,
    api_ready,
    blocking,
    message,
  };
}

export function triggerKeepAlive(): Promise<{ ok: boolean; detail: string }> {
  return new Promise((resolve) => {
    const script = path.join(
      repoRoot(),
      "scripts",
      "control-center",
      "keep-argus-alive.ps1",
    );
    if (!fs.existsSync(script)) {
      resolve({ ok: false, detail: "keep-argus-alive.ps1 missing" });
      return;
    }
    const child = spawn(
      "powershell.exe",
      [
        "-NoProfile",
        "-NoLogo",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        script,
      ],
      {
        cwd: repoRoot(),
        windowsHide: true,
        env: { ...process.env, ARGUS_REPO_ROOT: repoRoot() },
      },
    );
    let detail = "";
    const timer = setTimeout(() => {
      child.kill();
      resolve({ ok: false, detail: detail.slice(-2000) || "keepalive timed out" });
    }, 120_000);
    child.stdout.on("data", (c: Buffer) => {
      detail += c.toString();
    });
    child.stderr.on("data", (c: Buffer) => {
      detail += c.toString();
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({ ok: false, detail: err.message });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({
        ok: code === 0,
        detail: detail.trim().slice(-4000),
      });
    });
  });
}

export function triggerStartArgus(): Promise<{ ok: boolean; detail: string }> {
  return new Promise((resolve) => {
    const script = path.join(
      repoRoot(),
      "scripts",
      "control-center",
      "start-argus.ps1",
    );
    if (!fs.existsSync(script)) {
      resolve({ ok: false, detail: "start-argus.ps1 missing" });
      return;
    }
    const child = spawn(
      "powershell.exe",
      [
        "-NoProfile",
        "-NoLogo",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-WindowStyle",
        "Hidden",
        "-File",
        script,
      ],
      {
        cwd: repoRoot(),
        windowsHide: true,
        env: {
          ...process.env,
          ARGUS_REPO_ROOT: repoRoot(),
          ARGUS_KEEP_DASHBOARD: "1",
          // Avoid nested self-update wipe while recovering from login.
          ARGUS_START_SELF_UPDATED: "1",
          // Never hard-reset the tree from a login recovery path.
          ARGUS_SKIP_START_SELF_UPDATE: "1",
        },
      },
    );
    let detail = "";
    const timer = setTimeout(() => {
      child.kill();
      resolve({ ok: false, detail: detail.slice(-2000) || "Start timed out" });
    }, 240_000);
    child.stdout.on("data", (c: Buffer) => {
      detail += c.toString();
    });
    child.stderr.on("data", (c: Buffer) => {
      detail += c.toString();
    });
    child.on("error", (err) => {
      clearTimeout(timer);
      resolve({ ok: false, detail: err.message });
    });
    child.on("close", (code) => {
      clearTimeout(timer);
      resolve({
        ok: code === 0,
        detail: detail.trim().slice(-4000),
      });
    });
  });
}
