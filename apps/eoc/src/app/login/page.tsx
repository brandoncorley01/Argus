import type { Metadata } from "next";
import Link from "next/link";
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
    redirect("/today");
  } catch {
    // show login
  }

  return (
    <div className="login-shell">
      <div className="login-panel rise" style={{ width: "min(520px, 100%)" }}>
        <h1>Argus</h1>
        <p className="lede">
          Sign in to run paper trading. Live trading stays locked.
        </p>

        <div className="desktop-banner-login">
          <p style={{ margin: "0 0 0.75rem", fontWeight: 600 }}>
            Need Start &amp; Stop on this PC?
          </p>
          <a
            className="btn control-btn control-btn-desktop desktop-download-cta"
            href="/api/founder/desktop-installer"
            download="Install-Argus-Desktop.cmd"
          >
            Download desktop installer
          </a>
          <p className="muted-note" style={{ marginBottom: 0 }}>
            Or open{" "}
            <Link href="/get-desktop">
              http://127.0.0.1:3000/get-desktop
            </Link>
          </p>
        </div>

        <LoginForm />
      </div>
    </div>
  );
}
