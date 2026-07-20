"use client";

import { useState, useTransition } from "react";

import { createUserAction, type ActionResult } from "@/lib/actions/auth";

export function CreateUserForm() {
  const [result, setResult] = useState<ActionResult | null>(null);
  const [pending, startTransition] = useTransition();

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (!window.confirm("Create this institutional user?")) return;
        const form = e.currentTarget;
        startTransition(async () => {
          const res = await createUserAction(new FormData(form));
          setResult(res);
          if (res.ok) form.reset();
        });
      }}
    >
      {result ? (
        <div className={`alert ${result.ok ? "ok" : "error"}`} role="status">
          {result.message}
        </div>
      ) : null}
      <div className="field">
        <label htmlFor="username">Username</label>
        <input id="username" name="username" required minLength={3} disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="email">Email (optional)</label>
        <input id="email" name="email" type="email" disabled={pending} />
      </div>
      <div className="field">
        <label htmlFor="password">Password (min 12)</label>
        <input
          id="password"
          name="password"
          type="password"
          required
          minLength={12}
          disabled={pending}
        />
      </div>
      <div className="field">
        <label htmlFor="role">Initial role</label>
        <select id="role" name="role" defaultValue="VIEWER" disabled={pending}>
          <option value="VIEWER">VIEWER</option>
          <option value="OPERATOR">OPERATOR</option>
          <option value="FOUNDER">FOUNDER</option>
        </select>
      </div>
      <button className="btn" type="submit" disabled={pending}>
        Create user
      </button>
    </form>
  );
}
