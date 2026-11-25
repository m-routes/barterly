"use client";

import { api } from "@/lib/api/client";

import type { EventName, EventProps } from "./events";

/**
 * Product analytics, only with consent.
 *
 * Nothing is sent until we know the person said yes to "Product analytics" in their
 * privacy settings; withdrawing stops sending at once (and the server deletes what it
 * had). Events are batched and sent every few seconds, or when the tab is hidden.
 */

type Queued = { name: EventName; occurred_at: string; props: Record<string, unknown> };

const FLUSH_MS = 5000;
const MAX_QUEUE = 100;

let consent: boolean | null = null; // null: not checked yet
let checking: Promise<boolean> | null = null;
let queue: Queued[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;

async function allowed(): Promise<boolean> {
  if (consent !== null) return consent;
  checking ??= api
    .GET("/api/v1/privacy/consents/")
    .then(({ data }) => {
      consent = Boolean(data?.find((c) => c.purpose === "analytics")?.granted);
      return consent;
    })
    .catch(() => false)
    .finally(() => {
      checking = null;
    });
  return checking;
}

/** Privacy settings call this when the person gives or withdraws analytics consent. */
export function setAnalyticsConsent(granted: boolean) {
  consent = granted;
  if (!granted) queue = [];
}

/** Forget everything (sign-out). */
export function resetAnalytics() {
  consent = null;
  queue = [];
  if (timer) clearTimeout(timer);
  timer = null;
}

export function track<N extends EventName>(name: N, props: EventProps[N]) {
  if (consent === false || typeof window === "undefined") return;
  queue.push({ name, occurred_at: new Date().toISOString(), props });
  if (queue.length > MAX_QUEUE) queue = queue.slice(-MAX_QUEUE);
  timer ??= setTimeout(() => void flush(), FLUSH_MS);
}

export async function flush(): Promise<void> {
  if (timer) clearTimeout(timer);
  timer = null;
  if (queue.length === 0) return;
  if (!(await allowed())) {
    queue = [];
    return;
  }
  const events = queue.splice(0, 50);
  try {
    const { data } = await api.POST("/api/v1/analytics/events/", {
      body: {
        platform: "web",
        app_version: process.env.NEXT_PUBLIC_GIT_SHA?.slice(0, 12) ?? "",
        events,
      },
    });
    if (data && !data.consent) setAnalyticsConsent(false);
  } catch {
    // Analytics never gets in the way: drop the batch.
  }
  if (queue.length) timer = setTimeout(() => void flush(), FLUSH_MS);
}

if (typeof document !== "undefined") {
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") void flush();
  });
}
