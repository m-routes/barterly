import type { NextConfig } from "next";

import { staticSecurityHeaders } from "./src/lib/security/headers";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Self-contained server bundle for the Docker image (web/Dockerfile).
  output: "standalone",
  poweredByHeader: false,
  // The API's paths end in "/" (Django). Keep them as written instead of redirecting
  // /api/v1/me/ to /api/v1/me on every call.
  skipTrailingSlashRedirect: true,
  // Build-time integrity hashes on every script file (see src/lib/security/headers.ts).
  experimental: { sri: { algorithm: "sha256" } },
  // CSP, HSTS, nosniff, framing and Permissions-Policy on every response.
  async headers() {
    return [
      {
        source: "/:path*",
        headers: staticSecurityHeaders(process.env.NODE_ENV === "production", {
          // Prerendered pages inline their RSC payload, which no nonce can reach
          // (docs/security.md, "Web CSP"). Everything else in the policy is strict.
          inlineScripts: true,
          tileUrl: process.env.NEXT_PUBLIC_MAP_TILE_URL,
        }),
      },
    ];
  },
};

export default nextConfig;
