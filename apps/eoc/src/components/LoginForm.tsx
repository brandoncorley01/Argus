"use client";

import { useState, useTransition } from "react";

export function LoginForm() {
  const [message, setMessage] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

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
          try {
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
      {message ? (
        <div className="alert error" role="alert">
          {message}
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="identifier">Username or email</label>
        <input
          id="identifier"
          name="identifier"
          autoComplete="username"
          required
          disabled={pending}
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
          disabled={pending}
        />
      </div>
      <button className="btn" type="submit" disabled={pending}>
        {pending ? "Signing in…" : "Sign in"}
      </button>
    </form>
  );
}
