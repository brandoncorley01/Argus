import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Control Center opens http://127.0.0.1:3000; next dev defaults to localhost.
  // Without this, Server Actions (login) fail with "Failed to fetch".
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
