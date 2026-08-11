import { NextResponse } from "next/server";

import { ARGUS_UI_BUILD } from "@/lib/build";

/** Alias for clients that prefer /api/* paths. */
export const dynamic = "force-dynamic";
export const revalidate = 0;

export function GET() {
  return new NextResponse(`${ARGUS_UI_BUILD}\n`, {
    status: 200,
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-store, max-age=0",
    },
  });
}
