import { cookies } from "next/headers";

export const SESSION_COOKIE = "argus_session";
export const CSRF_COOKIE = "argus_csrf";

export function apiBaseUrl(): string {
  return (
    process.env.ARGUS_API_BASE_URL?.replace(/\/$/, "") ||
    "http://127.0.0.1:8000"
  );
}

export async function sessionCookieHeader(): Promise<string | undefined> {
  const jar = await cookies();
  const session = jar.get(SESSION_COOKIE)?.value;
  if (!session) return undefined;
  return `${SESSION_COOKIE}=${session}`;
}

export async function csrfToken(): Promise<string | undefined> {
  const jar = await cookies();
  return jar.get(CSRF_COOKIE)?.value;
}

export function parseSetCookieHeaders(
  headers: Headers,
): { name: string; value: string; attrs: string }[] {
  const raw = headers.getSetCookie?.() ?? [];
  if (raw.length === 0) {
    const single = headers.get("set-cookie");
    if (single) raw.push(single);
  }
  return raw.map((line) => {
    const [pair, ...rest] = line.split(";");
    const eq = pair.indexOf("=");
    const name = pair.slice(0, eq).trim();
    const value = pair.slice(eq + 1).trim();
    return { name, value, attrs: rest.join(";") };
  });
}
