import type { Metadata } from "next";
import { redirect } from "next/navigation";

import { LoginForm } from "@/components/LoginForm";
import { apiFetch } from "@/lib/server/api";
import type { CurrentUser } from "@/lib/types";

export const metadata: Metadata = {
  title: "Sign in",
};

export default async function LoginPage() {
  try {
    await apiFetch<CurrentUser>("/api/v1/auth/me");
    redirect("/overview");
  } catch {
    // show login
  }

  return (
    <div className="login-shell">
      <div className="login-panel rise">
        <h1>Argus</h1>
        <p className="lede">
          Executive Operations Center. Authenticate against the institutional
          control plane. No fabricated status is shown here.
        </p>
        <LoginForm />
      </div>
    </div>
  );
}
