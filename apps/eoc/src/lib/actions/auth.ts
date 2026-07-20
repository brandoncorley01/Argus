"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { apiFetch, SESSION_COOKIE } from "@/lib/server/api";
import { CSRF_COOKIE, apiBaseUrl, parseSetCookieHeaders } from "@/lib/server/env";
import type { CreateUserPayload } from "@/lib/actions/types";
import type {
  CurrentUser,
  InstitutionalRole,
  LoginResponse,
  OperatingMode,
} from "@/lib/types";
import { ApiClientError } from "@/lib/types";

async function setSessionFromLogin(login: LoginResponse, setCookieLines: string[]) {
  const jar = await cookies();
  const parsed = setCookieLines.length
    ? setCookieLines.map((line) => {
        const [pair] = line.split(";");
        const eq = pair.indexOf("=");
        return {
          name: pair.slice(0, eq).trim(),
          value: pair.slice(eq + 1).trim(),
        };
      })
    : [];

  const session = parsed.find((c) => c.name === SESSION_COOKIE);
  if (session) {
    jar.set(SESSION_COOKIE, session.value, {
      httpOnly: true,
      sameSite: "lax",
      path: "/",
      secure: process.env.SESSION_COOKIE_SECURE === "true",
    });
  }

  jar.set(CSRF_COOKIE, login.csrf_token, {
    httpOnly: true,
    sameSite: "lax",
    path: "/",
    secure: process.env.SESSION_COOKIE_SECURE === "true",
  });
}

export type ActionResult =
  | { ok: true; message?: string }
  | { ok: false; message: string };

export async function loginAction(
  _prev: ActionResult | null,
  formData: FormData,
): Promise<ActionResult> {
  const identifier = String(formData.get("identifier") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  if (!identifier || !password) {
    return { ok: false, message: "Identifier and password are required." };
  }

  try {
    const res = await fetch(`${apiBaseUrl()}/api/v1/auth/login`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ identifier, password }),
      cache: "no-store",
    });

    const text = await res.text();
    let body: unknown = null;
    if (text) {
      try {
        body = JSON.parse(text);
      } catch {
        body = text;
      }
    }

    if (!res.ok) {
      const detail =
        body && typeof body === "object" && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : "Invalid credentials";
      return { ok: false, message: detail };
    }

    const login = body as LoginResponse;
    const setCookies = parseSetCookieHeaders(res.headers).map(
      (c) => `${c.name}=${c.value}`,
    );
    // Prefer raw getSetCookie if available for full lines
    const raw = res.headers.getSetCookie?.() ?? setCookies;
    await setSessionFromLogin(login, raw);
    redirect("/overview");
  } catch (err) {
    if (err && typeof err === "object" && "digest" in err) {
      throw err; // Next.js redirect
    }
    return {
      ok: false,
      message: "Unable to reach the Argus API. Confirm the control plane is running.",
    };
  }
}

export async function logoutAction(): Promise<void> {
  try {
    await apiFetch<void>("/api/v1/auth/logout", { method: "POST" });
  } catch {
    // Clear local cookies even if API logout fails
  }
  const jar = await cookies();
  jar.delete(SESSION_COOKIE);
  jar.delete(CSRF_COOKIE);
  redirect("/login");
}

export async function requireUser(): Promise<CurrentUser> {
  try {
    return await apiFetch<CurrentUser>("/api/v1/auth/me");
  } catch (err) {
    if (err instanceof ApiClientError && (err.status === 401 || err.status === 403)) {
      redirect("/login");
    }
    redirect("/login");
  }
}

export async function transitionModeAction(formData: FormData): Promise<ActionResult> {
  const target_mode = String(formData.get("target_mode") ?? "") as OperatingMode;
  const reason = String(formData.get("reason") ?? "").trim();
  const expected = formData.get("expected_state_version");
  if (!target_mode || !reason) {
    return { ok: false, message: "Target mode and reason are required." };
  }
  try {
    await apiFetch("/api/v1/operating-mode/transition", {
      method: "POST",
      body: {
        target_mode,
        reason,
        expected_state_version: expected ? Number(expected) : null,
      },
      idempotencyKey: crypto.randomUUID(),
    });
    return { ok: true, message: `Transition to ${target_mode} submitted.` };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Transition failed.",
    };
  }
}

export async function emergencyStopAction(formData: FormData): Promise<ActionResult> {
  const reason = String(formData.get("reason") ?? "").trim();
  if (!reason) return { ok: false, message: "Reason is required." };
  const expected = formData.get("expected_state_version");
  try {
    await apiFetch("/api/v1/operating-mode/emergency-stop", {
      method: "POST",
      body: {
        reason,
        expected_state_version: expected ? Number(expected) : null,
      },
      idempotencyKey: crypto.randomUUID(),
    });
    return { ok: true, message: "Emergency stop submitted." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Emergency stop failed.",
    };
  }
}

export async function emergencyRecoverAction(formData: FormData): Promise<ActionResult> {
  const reason = String(formData.get("reason") ?? "").trim();
  if (!reason) return { ok: false, message: "Reason is required." };
  const expected = formData.get("expected_state_version");
  try {
    await apiFetch("/api/v1/operating-mode/emergency-stop/recover", {
      method: "POST",
      body: {
        reason,
        expected_state_version: expected ? Number(expected) : null,
      },
    });
    return { ok: true, message: "Recovery submitted." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Recovery failed.",
    };
  }
}

export async function initializeModeAction(): Promise<ActionResult> {
  try {
    await apiFetch("/api/v1/operating-mode/initialize", {
      method: "POST",
    });
    return { ok: true, message: "System initialized." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Initialize failed.",
    };
  }
}

export async function createIncidentAction(formData: FormData): Promise<ActionResult> {
  const title = String(formData.get("title") ?? "").trim();
  const description = String(formData.get("description") ?? "").trim() || null;
  const severity = String(formData.get("severity") ?? "medium");
  if (!title) return { ok: false, message: "Title is required." };
  try {
    await apiFetch("/api/v1/incidents", {
      method: "POST",
      body: { title, description, severity },
    });
    return { ok: true, message: "Incident opened." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Create incident failed.",
    };
  }
}

export async function transitionIncidentAction(
  formData: FormData,
): Promise<ActionResult> {
  const id = String(formData.get("incident_id") ?? "");
  const target_status = String(formData.get("target_status") ?? "");
  const note = String(formData.get("note") ?? "").trim() || null;
  if (!id || !target_status) {
    return { ok: false, message: "Incident and target status are required." };
  }
  try {
    await apiFetch(`/api/v1/incidents/${id}/transition`, {
      method: "POST",
      body: { target_status, note },
    });
    return { ok: true, message: "Incident transitioned." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Transition failed.",
    };
  }
}

export async function createUserAction(formData: FormData): Promise<ActionResult> {
  const username = String(formData.get("username") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const email = String(formData.get("email") ?? "").trim() || null;
  const role = String(formData.get("role") ?? "VIEWER") as InstitutionalRole;
  if (!username || password.length < 12) {
    return {
      ok: false,
      message: "Username and password (min 12 characters) are required.",
    };
  }
  const payload: CreateUserPayload = {
    username,
    password,
    email,
    roles: [role],
  };
  try {
    await apiFetch("/api/v1/auth/users", { method: "POST", body: payload });
    return { ok: true, message: `User ${username} created.` };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Create user failed.",
    };
  }
}

export async function runSupervisorCycleAction(): Promise<ActionResult> {
  try {
    await apiFetch("/api/v1/health/supervisor/run-cycle", {
      method: "POST",
      body: {},
    });
    return { ok: true, message: "Supervisor cycle requested." };
  } catch (err) {
    return {
      ok: false,
      message: err instanceof Error ? err.message : "Cycle failed.",
    };
  }
}
