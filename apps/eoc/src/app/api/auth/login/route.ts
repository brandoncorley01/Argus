import { NextResponse } from "next/server";

import { SESSION_COOKIE } from "@/lib/server/api";
import { CSRF_COOKIE, apiBaseUrl, parseSetCookieHeaders } from "@/lib/server/env";
import type { LoginResponse } from "@/lib/types";

export const dynamic = "force-dynamic";

/**
 * Stable login endpoint (not a Server Action). Survives Next.js HMR / EOC
 * restarts that invalidate old action IDs and look like a login "timeout".
 */
export async function POST(request: Request) {
  let identifier = "";
  let password = "";
  try {
    const body = (await request.json()) as {
      identifier?: unknown;
      password?: unknown;
    };
    identifier = String(body.identifier ?? "").trim();
    password = String(body.password ?? "");
  } catch {
    return NextResponse.json(
      { ok: false, message: "Invalid login request." },
      { status: 400 },
    );
  }

  if (!identifier || !password) {
    return NextResponse.json(
      { ok: false, message: "Identifier and password are required." },
      { status: 400 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(`${apiBaseUrl()}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ identifier, password }),
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
  } catch (err) {
    const timedOut =
      err instanceof Error &&
      (err.name === "TimeoutError" || err.name === "AbortError");
    return NextResponse.json(
      {
        ok: false,
        message: timedOut
          ? "Argus API timed out. Open Docker Desktop, press Start Argus, then try again."
          : "Unable to reach the Argus API. Open Docker Desktop if needed, press Start Argus, then try again.",
      },
      { status: 503 },
    );
  }

  const text = await upstream.text();
  let body: unknown = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }

  if (!upstream.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : "Invalid credentials";
    return NextResponse.json(
      { ok: false, message: detail },
      { status: upstream.status === 401 ? 401 : 400 },
    );
  }

  const login = body as LoginResponse;
  const parsed = parseSetCookieHeaders(upstream.headers);
  const session = parsed.find((c) => c.name === SESSION_COOKIE);
  const secure = process.env.SESSION_COOKIE_SECURE === "true";

  const res = NextResponse.json({ ok: true, message: "Signed in." });
  if (session) {
    res.cookies.set(SESSION_COOKIE, session.value, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure,
    });
  }
  res.cookies.set(CSRF_COOKIE, login.csrf_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure,
  });
  return res;
}
