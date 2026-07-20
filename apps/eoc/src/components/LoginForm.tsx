"use client";

import { useActionState } from "react";

import { loginAction, type ActionResult } from "@/lib/actions/auth";

const initial: ActionResult | null = null;

export function LoginForm() {
  const [state, formAction, pending] = useActionState(loginAction, initial);

  return (
    <form action={formAction} noValidate>
      {state && !state.ok ? (
        <div className="alert error" role="alert">
          {state.message}
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
