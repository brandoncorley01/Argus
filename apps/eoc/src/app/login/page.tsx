import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { LoginForm } from "@/components/LoginForm";
import { apiFetch } from "@/lib/server/api";
import type { CurrentUser } from "@/lib/types";

export const metadata: Metadata = {
  title: "Sign in",
};

const REASONS: Record<string, string> = {
  expired:
    "Your session ended, so Argus signed you out. Paper trading kept running in the background — sign in to see the current state.",
  unreachable:
    "Argus could not reach the control plane, so it signed you out. Confirm the API is running, then sign in again.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}) {
  let authenticated = false;
  try {
    await apiFetch<CurrentUser>("/api/v1/auth/me");
    authenticated = true;
  } catch {
    // show login
  }
  // redirect() throws, so it must run outside the catch that swallows errors.
  if (authenticated) redirect("/today");

  const { reason } = await searchParams;
  const notice = reason ? REASONS[reason] : null;

  return (
    <div className="login-shell">
      <div className="login-panel rise" style={{ width: "min(520px, 100%)" }}>
        <h1>Argus</h1>
        <p className="lede">
          Sign in to run paper trading. Live trading stays locked.
        </p>
        {notice ? (
          <p className="login-notice" role="status">
            {notice}
          </p>
        ) : null}
        <LoginForm />
      </div>
    </div>
  );
}
