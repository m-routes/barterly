/**
 * Refreshes the session cookies, once at a time.
 *
 * Refresh tokens rotate and the old one is blacklisted, so two refreshes racing with
 * the same cookie would sign the person out. Calls in this tab share one promise;
 * across tabs a Web Lock serialises them, and a tab that waited on the lock skips its
 * own refresh if another tab refreshed after this one's 401.
 */

export const REFRESH_PATH = "/api/v1/auth/refresh/";
const LOCK_NAME = "barterly-session-refresh";
const STAMP_KEY = "barterly:refreshed-at";

let inFlight: Promise<boolean> | null = null;

function readStamp(): number {
  try {
    return Number(window.localStorage.getItem(STAMP_KEY)) || 0;
  } catch {
    return 0;
  }
}

function writeStamp(): void {
  try {
    window.localStorage.setItem(STAMP_KEY, String(Date.now()));
  } catch {
    // Storage can be unavailable (private mode); the lock still serialises.
  }
}

async function postRefresh(): Promise<boolean> {
  try {
    const response = await fetch(REFRESH_PATH, {
      method: "POST",
      credentials: "same-origin",
      headers: { accept: "application/json" },
    });
    if (response.ok) writeStamp();
    return response.ok;
  } catch {
    return false;
  }
}

async function refreshWithLock(startedAt: number): Promise<boolean> {
  const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
  if (!locks) return postRefresh();
  return locks.request(LOCK_NAME, async () => {
    // Another tab refreshed after this one hit its 401: those cookies are ours too.
    if (readStamp() >= startedAt) return true;
    return postRefresh();
  });
}

/** True if the session was refreshed (or another tab just did it). */
export function refreshSession(): Promise<boolean> {
  inFlight ??= refreshWithLock(Date.now()).finally(() => {
    inFlight = null;
  });
  return inFlight;
}
