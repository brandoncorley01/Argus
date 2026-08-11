import { NextResponse } from "next/server";

import { ARGUS_UI_BUILD } from "@/lib/build";

/**
 * Always-available build stamp for Founder proof / Home chip.
 * Public file apps/eoc/public/argus-build.txt can be missing on stale PC trees
 * (Next then 404s). This route never 404s while this dashboard process is up.
 */
export const dynamic = "force-dynamic";
export const revalidate = 0;

export function GET() {
  const body = `${ARGUS_UI_BUILD}\n`;
  return new NextResponse(body, {
    status: 200,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
    },
  });
}
