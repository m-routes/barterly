import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  // Self-contained server bundle for the Docker image (web/Dockerfile).
  output: "standalone",
  poweredByHeader: false,
};

export default nextConfig;
