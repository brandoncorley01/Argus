import { NextResponse } from "next/server";

import {
  isRecoveryCooldownActive,
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
    status: report.api_health ? 200 : 503,
  });
}

/**
 * Recover when API is unreachable from login.
 * - desired=Running → keepalive (infra + API + worker)
 * - desired=Stopped → Start Argus (sets desired Running)
 */
export async function POST() {
  const before = await probeReachability();
  if (before.api_health) {
    return NextResponse.json({ ...before, recovering: false });
  }

  if (isRecoveryCooldownActive(10)) {
    const after = await probeReachability();
    return NextResponse.json(
      {
        ...after,
        recovering: false,
        message:
          "Recovery already ran in the last few minutes. Wait, then try sign-in — or run Boot Argus from the Desktop.",
      },
      { status: after.api_health ? 200 : 503 },
    );
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
      message: after.api_health
        ? "Argus API recovered. You can sign in."
        : after.message,
    },
    { status: after.api_health ? 200 : 503 },
  );
}
