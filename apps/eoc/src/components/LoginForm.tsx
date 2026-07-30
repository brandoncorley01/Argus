"use client";

import { useEffect, useRef, useState, useTransition } from "react";

type Reachability = {
  desired_running?: boolean;
  docker_engine?: boolean;
  postgres?: boolean;
  redis?: boolean;
  api_health?: boolean;
  api_ready?: boolean;
  blocking?: string;
  message?: string;
  recovering?: boolean;
  recover_ok?: boolean;
};

function formatDeps(r: Reachability | null): string {
  if (!r) return "";
  const bit = (ok: boolean | undefined, label: string) =>
    `${label}:${ok ? "up" : "down"}`;
  return [
    bit(r.docker_engine, "Docker"),
    bit(r.postgres, "Postgres"),
    bit(r.redis, "Redis"),
    bit(r.api_ready, "API"),
  ].join(" · ");
}

export function LoginForm() {
  const [message, setMessage] = useState<string | null>(null);
  const [statusLine, setStatusLine] = useState<string | null>(null);
  const [apiReady, setApiReady] = useState(false);
  const [desiredRunning, setDesiredRunning] = useState(false);
  const [pending, startTransition] = useTransition();
  const [recovering, setRecovering] = useState(false);
  const autoRecoverStarted = useRef(false);

  async function runRecover() {
    setRecovering(true);
    setMessage("Recovering Argus (Docker / Postgres / Redis / API)…");
    try {
      const res = await fetch("/api/auth/reachability", {
        method: "POST",
        cache: "no-store",
        signal: AbortSignal.timeout(240_000),
      });
      const body = (await res.json().catch(() => null)) as Reachability | null;
      if (body) {
        setStatusLine(formatDeps(body));
        setApiReady(Boolean(body.api_ready));
        setDesiredRunning(Boolean(body.desired_running));
        setMessage(
          body.api_ready
            ? "Argus API is ready. Sign in when ready."
            : body.message ||
                "Recovery finished but the API is still down. Open Docker Desktop and use Start Argus.",
        );
        return Boolean(body.api_ready);
      }
      return false;
    } catch {
      setMessage(
        "Recovery timed out. Open Docker Desktop if needed, press Start Argus, then try again.",
      );
      return false;
    } finally {
      setRecovering(false);
    }
  }

  useEffect(() => {
    let cancelled = false;

    async function refresh() {
      try {
        const res = await fetch("/api/auth/reachability", {
          cache: "no-store",
          signal: AbortSignal.timeout(8_000),
        });
        const body = (await res.json().catch(() => null)) as Reachability | null;
        if (cancelled || !body) return;
        setStatusLine(formatDeps(body));
        setApiReady(Boolean(body.api_ready));
        setDesiredRunning(Boolean(body.desired_running));
        if (!body.api_ready) {
          setMessage(body.message || "Argus API is unreachable.");
          // Only auto-recover when Founder already asked Argus to stay Running.
          if (body.desired_running && !autoRecoverStarted.current) {
            autoRecoverStarted.current = true;
            void runRecover();
          }
        } else {
          setMessage(null);
        }
      } catch {
        if (!cancelled) {
          setStatusLine("Docker:? · Postgres:? · Redis:? · API:down");
          setMessage("Unable to probe Argus reachability from this page.");
        }
      }
    }

    void refresh();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <form
      noValidate
      onSubmit={(event) => {
        event.preventDefault();
        setMessage(null);
        const form = event.currentTarget;
        const data = new FormData(form);
        const identifier = String(data.get("identifier") ?? "").trim();
        const password = String(data.get("password") ?? "");
        if (!identifier || !password) {
          setMessage("Identifier and password are required.");
          return;
        }

        startTransition(async () => {
          const attemptLogin = async () => {
            const res = await fetch("/api/auth/login", {
              method: "POST",
              headers: {
                Accept: "application/json",
                "Content-Type": "application/json",
              },
              body: JSON.stringify({ identifier, password }),
              cache: "no-store",
              signal: AbortSignal.timeout(25_000),
            });
            const body = (await res.json().catch(() => null)) as {
              ok?: boolean;
              message?: string;
            } | null;
            return { res, body };
          };

          try {
            let { res, body } = await attemptLogin();
            if (res.status === 503) {
              setMessage("API unreachable — recovering, then retrying sign-in…");
              await runRecover();
              const deadline = Date.now() + 45_000;
              while (Date.now() < deadline) {
                ({ res, body } = await attemptLogin());
                if (res.ok && body?.ok) break;
                if (res.status !== 503) break;
                await new Promise((r) => setTimeout(r, 2500));
              }
            }
            if (!res.ok || !body?.ok) {
              setMessage(
                body?.message ||
                  (res.status >= 500
                    ? "Unable to reach the Argus API. Confirm Argus is Running."
                    : "Sign in failed."),
              );
              return;
            }
            window.location.assign("/today");
          } catch (err) {
            const timedOut =
              err instanceof Error &&
              (err.name === "TimeoutError" || err.name === "AbortError");
            setMessage(
              timedOut
                ? "Login timed out. Hard-refresh this page (Ctrl+F5), then try again."
                : "Unable to reach Argus. Confirm it is Running, then try again.",
            );
          }
        });
      }}
    >
      {statusLine ? (
        <p className="lede" style={{ marginBottom: "0.75rem", fontSize: "0.85rem" }}>
          {statusLine}
          {recovering ? " · recovering…" : ""}
        </p>
      ) : null}
      {message ? (
        <div
          className={`alert ${apiReady && message.includes("ready") ? "ok" : "error"}`}
          role="status"
        >
          {message}
        </div>
      ) : null}
      {!apiReady ? (
        <button
          className="btn secondary"
          type="button"
          style={{ marginBottom: "1rem", width: "100%" }}
          disabled={recovering || pending}
          onClick={() => {
            void runRecover();
          }}
        >
          {recovering
            ? desiredRunning
              ? "Recovering…"
              : "Starting Argus…"
            : desiredRunning
              ? "Recover Argus"
              : "Start Argus"}
        </button>
      ) : null}
      <div className="field">
        <label htmlFor="identifier">Username or email</label>
        <input
          id="identifier"
          name="identifier"
          autoComplete="username"
          required
          disabled={pending || recovering}
        />
      </div>
      <div className="field">
        <label htmlFor="password">Password</label>
        <input
          id="password"
          name="password"
          type="password"
          autoComplete="current-password"
          required
          disabled={pending || recovering}
        />
      </div>
      <button className="btn" type="submit" disabled={pending || recovering}>
        {pending ? "Signing in…" : recovering ? "Recovering…" : "Sign in"}
      </button>
    </form>
  );
}
