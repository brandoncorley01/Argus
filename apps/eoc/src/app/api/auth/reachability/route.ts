import { NextResponse } from "next/server";

import {
  probeReachability,
  triggerKeepAlive,
  triggerStartArgus,
} from "@/lib/server/reachability";

export const dynamic = "force-dynamic";

/**
 * Real dependency probes for the login screen. Never invents a healthy API.
 */
export async function GET() {
  const report = await probeReachability();
  return NextResponse.json(report, {
    status: report.api_ready ? 200 : 503,
  });
}

/**
 * Recover when API is unreachable from login.
 * - desired=Running → keepalive (infra + API + worker)
 * - desired=Stopped → Start Argus (sets desired Running)
 */
export async function POST() {
  const before = await probeReachability();
  if (before.api_ready) {
    return NextResponse.json({ ...before, recovering: false });
  }

  const result = before.desired_running
    ? await triggerKeepAlive()
    : await triggerStartArgus();

  const after = await probeReachability();
  return NextResponse.json(
    {
      ...after,
      recovering: true,
      recover_ok: result.ok,
      recover_detail: result.detail.slice(-1500),
      message: after.api_ready
        ? "Argus API recovered. You can sign in."
        : after.message,
    },
    { status: after.api_ready ? 200 : 503 },
  );
}
