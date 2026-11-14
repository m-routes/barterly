import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Self-contained server bundle for the Docker image (web/Dockerfile).
  output: "standalone",
  poweredByHeader: false,
  // The API's paths end in "/" (Django). Keep them as written instead of redirecting
  // /api/v1/me/ to /api/v1/me on every call.
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
