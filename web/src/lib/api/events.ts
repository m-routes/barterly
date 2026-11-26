import type { ApiError } from "./errors";

/**
 * The global error handler: the API client reports here, and the app shell listens.
 *
 * - "error": a failure no screen is expected to handle itself (5xx, 429, offline,
 *   403). The shell shows a toast.
 * - "session-expired": the refresh token is gone or rejected. The shell sends the
 *   person to /login.
 * - "notice": a message for the person from a screen that has nowhere else to put it
 *   (an optimistic change that the server refused and was put back). Shown as a toast.
 */
export type ApiEvent =
  | { type: "error"; error: ApiError }
  | { type: "session-expired" }
  | { type: "notice"; message: string };

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

/** Show a short message in the toaster. */
export function notify(message: string): void {
  emitApiEvent({ type: "notice", message });
}
