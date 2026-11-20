import type { MetadataRoute } from "next";

/** Installs the console as an app; it opens on arrivals, which works offline. */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Barterly for hosts",
    short_name: "Barterly",
    description: "Check talent in, even without signal.",
    start_url: "/console/arrivals",
    scope: "/",
    display: "standalone",
    background_color: "#f4efe6",
    theme_color: "#1f2a24",
    icons: [{ src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
  };
}
