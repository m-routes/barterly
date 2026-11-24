import * as Sentry from "@sentry/nextjs";

import { DATA_COLLECTION, scrubEvent } from "@/lib/observability/scrub";

/**
 * Browser error reporting. The settings come from /api/sentry-config at runtime (see
 * that route); nothing is reported when the environment has no DSN.
 */
async function start() {
  try {
    const response = await fetch("/api/sentry-config");
    const config = (await response.json()) as {
      dsn: string | null;
      environment?: string;
      release?: string;
    };
    if (!config.dsn) return;
    Sentry.init({
      dsn: config.dsn,
      environment: config.environment,
      release: config.release,
      tunnel: "/monitoring",
      dataCollection: { ...DATA_COLLECTION, httpBodies: [] },
      tracesSampleRate: 0,
      beforeSend: (event) => scrubEvent(event),
      beforeBreadcrumb: (crumb) => scrubEvent(crumb as never),
    });
  } catch {
    // Error reporting must never break the page.
  }
}

if (typeof window !== "undefined") void start();

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
