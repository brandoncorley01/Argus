import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

export function middleware(request: NextRequest) {
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-pathname", request.nextUrl.pathname);
  return NextResponse.next({
    request: { headers: requestHeaders },
  });
}

export const config = {
  matcher: [
    "/overview/:path*",
    "/operations/:path*",
    "/services/:path*",
    "/workers/:path*",
    "/incidents/:path*",
    "/market/:path*",
    "/strategies/:path*",
    "/paper/:path*",
    "/micro-live/:path*",
    "/audit/:path*",
    "/configurations/:path*",
    "/policies/:path*",
    "/administration/:path*",
  ],
};
