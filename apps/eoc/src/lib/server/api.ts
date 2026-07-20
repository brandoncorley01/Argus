import {
  apiBaseUrl,
  csrfToken,
  parseSetCookieHeaders,
  SESSION_COOKIE,
  sessionCookieHeader,
} from "@/lib/server/env";
import { ApiClientError, type ApiErrorBody } from "@/lib/types";

export type ProxyOptions = {
  method?: string;
  body?: unknown;
  searchParams?: Record<string, string | number | undefined | null>;
  idempotencyKey?: string;
  requireCsrf?: boolean;
  /** Optional raw Cookie header override (e.g. login response capture). */
  cookieHeader?: string;
  captureSetCookies?: (cookies: { name: string; value: string }[]) => void;
};

function buildUrl(path: string, searchParams?: ProxyOptions["searchParams"]): string {
  const url = new URL(
    path.startsWith("/") ? path : `/${path}`,
    `${apiBaseUrl()}/`,
  );
  if (searchParams) {
    for (const [k, v] of Object.entries(searchParams)) {
      if (v === undefined || v === null || v === "") continue;
      url.searchParams.set(k, String(v));
    }
  }
  return url.toString();
}

function errorMessage(status: number, body: unknown): string {
  if (body && typeof body === "object") {
    const detail = (body as ApiErrorBody).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
  }
  return `API request failed (${status})`;
}

/**
 * Server-side call to the FastAPI control plane.
 * Forwards session cookie; attaches CSRF on mutating methods.
 * UI role checks never replace backend authorization.
 */
export async function apiFetch<T>(
  path: string,
  options: ProxyOptions = {},
): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    Accept: "application/json",
  };

  const cookie = options.cookieHeader ?? (await sessionCookieHeader());
  if (cookie) headers.Cookie = cookie;

  const mutating = !["GET", "HEAD", "OPTIONS", "TRACE"].includes(method);
  if (mutating || options.requireCsrf) {
    const csrf = await csrfToken();
    if (csrf) headers["X-CSRF-Token"] = csrf;
  }
  if (options.idempotencyKey) {
    headers["Idempotency-Key"] = options.idempotencyKey;
  }
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(buildUrl(path, options.searchParams), {
    method,
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

  if (options.captureSetCookies) {
    const setCookies = parseSetCookieHeaders(res.headers);
    options.captureSetCookies(
      setCookies.map((c) => ({ name: c.name, value: c.value })),
    );
  }

  if (res.status === 204) {
    return undefined as T;
  }

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
    throw new ApiClientError(res.status, errorMessage(res.status, body), body);
  }

  return body as T;
}

export { SESSION_COOKIE, apiBaseUrl };
