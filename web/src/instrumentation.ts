import * as Sentry from "@sentry/nextjs";

import { DATA_COLLECTION, scrubEvent } from "@/lib/observability/scrub";

/** Server-side error reporting (Node and edge). Off unless SENTRY_DSN is set. */
export async function register() {
  const dsn = process.env.SENTRY_DSN?.trim();
  if (!dsn) return;
  Sentry.init({
    dsn,
    environment: process.env.BARTERLY_ENV?.trim() || "local",
    release: process.env.SENTRY_RELEASE?.trim() || undefined,
    dataCollection: { ...DATA_COLLECTION, httpBodies: [] },
    tracesSampleRate: 0,
    beforeSend: (event) => scrubEvent(event),
  });
}

export const onRequestError = Sentry.captureRequestError;
