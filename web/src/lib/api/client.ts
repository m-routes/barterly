import createClient, { type Middleware } from "openapi-fetch";

import { ApiError, networkError, toApiError } from "./errors";
import { emitApiEvent } from "./events";
import { REFRESH_PATH, refreshSession } from "./refresh";
import type { paths } from "./schema";

/**
 * The typed API client. Paths, params and bodies come from the backend's OpenAPI
 * schema (web/openapi/schema.yaml → src/lib/api/schema.d.ts, `npm run api:types`).
 *
 * Calls go to this site's /api/v1/, which forwards them to Django with the access
 * token from an httpOnly cookie (src/lib/server/bff.ts).
 */

const AUTH_PATHS = ["/api/v1/auth/exchange/", REFRESH_PATH, "/api/v1/auth/logout/"];

function isAuthCall(url: string): boolean {
  const { pathname } = new URL(url, "http://localhost");
  return AUTH_PATHS.includes(pathname);
}

/**
 * fetch with one retry after a token refresh: a 401 means the access cookie expired
 * (or was never set); refresh it and replay the request once.
 */
export async function authFetch(request: Request): Promise<Response> {
  const replay = request.clone();
  const response = await fetch(request);
  if (response.status !== 401 || isAuthCall(request.url)) return response;

  if (await refreshSession()) return fetch(replay);
  emitApiEvent({ type: "session-expired" });
  return response;
}

/** Statuses a screen isn't expected to handle itself; the shell shows a toast. */
function isGlobalFailure(status: number): boolean {
  return status >= 500 || status === 429 || status === 403;
}

const globalErrors: Middleware = {
  async onResponse({ response }) {
    if (response.ok || !isGlobalFailure(response.status)) return undefined;
    const body: unknown = await response
      .clone()
      .json()
      .catch(() => null);
    emitApiEvent({ type: "error", error: toApiError(response, body) });
    return undefined;
  },
  onError() {
    const error = networkError();
    emitApiEvent({ type: "error", error });
    return error;
  },
};

function baseUrl(): string {
  return typeof window === "undefined" ? "http://localhost" : window.location.origin;
}

export function makeApiClient(fetchImpl: (request: Request) => Promise<Response> = authFetch) {
  const client = createClient<paths>({
    baseUrl: baseUrl(),
    fetch: fetchImpl,
    credentials: "same-origin",
    headers: { accept: "application/json" },
  });
  client.use(globalErrors);
  return client;
}

export const api = makeApiClient();

type Result<T> = { data?: T; error?: unknown; response: Response };

/**
 * Resolve an openapi-fetch call to its data, or throw an ApiError.
 *
 *     const me = await unwrap(api.GET("/api/v1/me/"));
 */
export async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await call;
  } catch (error) {
    throw error instanceof ApiError ? error : networkError();
  }
  if (!result.response.ok || result.error !== undefined) {
    throw toApiError(result.response, result.error);
  }
  return result.data as T;
}

/**
 * A create body. The schema reuses response components for requests, so read-only
 * fields (id, timestamps, status, nested lists) show up as required; the API ignores
 * them. This says so in one place instead of at every call.
 */
export function writeBody<T>(body: Partial<T>): T {
  return body as T;
}
