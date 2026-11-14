import type { ApiError } from "./errors";

/**
 * The global error handler: the API client reports here, and the app shell listens.
 *
 * - "error": a failure no screen is expected to handle itself (5xx, 429, offline,
 *   403). The shell shows a toast.
 * - "session-expired": the refresh token is gone or rejected. The shell sends the
 *   person to /login.
 */
export type ApiEvent = { type: "error"; error: ApiError } | { type: "session-expired" };

type Listener = (event: ApiEvent) => void;

const listeners = new Set<Listener>();

export function onApiEvent(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function emitApiEvent(event: ApiEvent): void {
  for (const listener of listeners) listener(event);
}
