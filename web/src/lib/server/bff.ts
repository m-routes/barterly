import "server-only";

import { NextResponse, type NextRequest } from "next/server";

import {
  ACCESS_COOKIE,
  REFRESH_COOKIE,
  clearedCookies,
  tokenCookies,
  type CookieSpec,
} from "./session-cookies";

/**
 * Backend-for-frontend: forwards /api/v1/* from the browser to the Django API.
 *
 * - The browser talks only to this origin, so the API needs no CORS.
 * - Tokens stay in httpOnly cookies: the access cookie becomes `Authorization: Bearer`,
 *   and the three auth endpoints are handled here so token values never reach JS.
 * - Unsafe methods must come from this origin (cookies are SameSite=Lax as well).
 */

const EXCHANGE = "/api/v1/auth/exchange/";
const REFRESH = "/api/v1/auth/refresh/";
const LOGOUT = "/api/v1/auth/logout/";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);
const FORWARD_REQUEST_HEADERS = ["accept", "accept-language", "content-type", "x-request-id"];
const FORWARD_RESPONSE_HEADERS = [
  "content-type",
  "retry-after",
  "x-request-id",
  "www-authenticate",
  "cache-control",
];
const UPSTREAM_TIMEOUT_MS = 30_000;

type Tokens = { access: string; refresh: string };

function errorResponse(status: number, code: string, message: string): NextResponse {
  return NextResponse.json({ code, message, details: {} }, { status });
}

function isSecure(request: NextRequest): boolean {
  return (
    request.nextUrl.protocol === "https:" || request.headers.get("x-forwarded-proto") === "https"
  );
}

function withCookies(response: NextResponse, cookies: CookieSpec[]): NextResponse {
  for (const spec of cookies) response.cookies.set(spec);
  return response;
}

/** Same-origin check for unsafe methods. Browsers always send Origin on these. */
function isSameOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  if (origin) return origin === request.nextUrl.origin;
  return request.headers.get("sec-fetch-site") !== "cross-site";
}

/** The API path for this request; Django's routes all end in a slash. */
function upstreamPath(request: NextRequest): string {
  const path = request.nextUrl.pathname;
  return path.endsWith("/") ? path : `${path}/`;
}

function forwardedFor(request: NextRequest): string | null {
  // Pass the browser's address chain on, so the API can see who the client was.
  return request.headers.get("x-forwarded-for");
}

async function callApi(
  apiUrl: string,
  path: string,
  init: { method: string; headers: Headers; body?: BodyInit | null; search?: string },
): Promise<Response | null> {
  try {
    return await fetch(`${apiUrl}${path}${init.search ?? ""}`, {
      method: init.method,
      headers: init.headers,
      body: init.body,
      redirect: "manual",
      cache: "no-store",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch {
    return null;
  }
}

function upstreamHeaders(request: NextRequest, access?: string): Headers {
  const headers = new Headers();
  for (const name of FORWARD_REQUEST_HEADERS) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }
  const xff = forwardedFor(request);
  if (xff) headers.set("x-forwarded-for", xff);
  if (access) headers.set("authorization", `Bearer ${access}`);
  return headers;
}

function jsonHeaders(request: NextRequest, access?: string): Headers {
  const headers = upstreamHeaders(request, access);
  headers.set("content-type", "application/json");
  headers.set("accept", "application/json");
  return headers;
}

function copyResponse(upstream: Response, body: BodyInit | null): NextResponse {
  const headers = new Headers();
  for (const name of FORWARD_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new NextResponse(body, { status: upstream.status, headers });
}

const unavailable = () =>
  errorResponse(502, "api_unavailable", "We couldn't reach Barterly. Try again in a moment.");

function isTokens(value: unknown): value is Tokens & Record<string, unknown> {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.access === "string" && typeof v.refresh === "string";
}

/** POST auth/exchange: store the tokens in cookies and return the rest of the body. */
async function exchange(request: NextRequest, apiUrl: string): Promise<NextResponse> {
  const upstream = await callApi(apiUrl, EXCHANGE, {
    method: "POST",
    headers: jsonHeaders(request),
    body: await request.text(),
  });
  if (!upstream) return unavailable();
  if (!upstream.ok) return copyResponse(upstream, await upstream.arrayBuffer());

  const body: unknown = await upstream.json();
  if (!isTokens(body)) return errorResponse(502, "bad_gateway", "Unexpected sign-in response.");
  const { access, refresh, ...rest } = body;
  const response = NextResponse.json(rest, { status: upstream.status });
  return withCookies(response, tokenCookies({ access, refresh }, isSecure(request)));
}

/** POST auth/refresh: rotate the cookies. The browser sends no token. */
async function refresh(request: NextRequest, apiUrl: string): Promise<NextResponse> {
  const secure = isSecure(request);
  const token = request.cookies.get(REFRESH_COOKIE)?.value;
  if (!token) {
    return errorResponse(401, "not_authenticated", "You're signed out.");
  }
  const upstream = await callApi(apiUrl, REFRESH, {
    method: "POST",
    headers: jsonHeaders(request),
    body: JSON.stringify({ refresh: token }),
  });
  if (!upstream) return unavailable();
  if (upstream.status === 401 || upstream.status === 400) {
    // The refresh token is spent, blacklisted or expired: the session is over.
    return withCookies(
      copyResponse(upstream, await upstream.arrayBuffer()),
      clearedCookies(secure),
    );
  }
  if (!upstream.ok) return copyResponse(upstream, await upstream.arrayBuffer());

  const body: unknown = await upstream.json();
  if (!isTokens(body)) return errorResponse(502, "bad_gateway", "Unexpected refresh response.");
  return withCookies(new NextResponse(null, { status: 204 }), tokenCookies(body, secure));
}

/** POST auth/logout: blacklist the refresh token if we can, and always clear the cookies. */
async function logout(request: NextRequest, apiUrl: string): Promise<NextResponse> {
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const token = request.cookies.get(REFRESH_COOKIE)?.value;
  if (token) {
    // Best effort: a failure here still signs this browser out.
    await callApi(apiUrl, LOGOUT, {
      method: "POST",
      headers: jsonHeaders(request, access),
      body: JSON.stringify({ refresh: token }),
    });
  }
  return withCookies(new NextResponse(null, { status: 204 }), clearedCookies(isSecure(request)));
}

/** Forward any other /api/v1/ call with the access token attached. */
async function forward(request: NextRequest, apiUrl: string): Promise<NextResponse> {
  const access = request.cookies.get(ACCESS_COOKIE)?.value;
  const hasBody = !SAFE_METHODS.has(request.method);
  const upstream = await callApi(apiUrl, upstreamPath(request), {
    method: request.method,
    headers: upstreamHeaders(request, access),
    body: hasBody ? await request.arrayBuffer() : null,
    search: request.nextUrl.search,
  });
  if (!upstream) return unavailable();
  const body = upstream.status === 204 || request.method === "HEAD" ? null : upstream.body;
  return copyResponse(upstream, body);
}

export async function handleApiRequest(
  request: NextRequest,
  apiUrl: string,
): Promise<NextResponse> {
  if (!SAFE_METHODS.has(request.method) && !isSameOrigin(request)) {
    return errorResponse(403, "cross_origin", "Requests must come from the Barterly site.");
  }
  const path = upstreamPath(request);
  if (request.method === "POST") {
    if (path === EXCHANGE) return exchange(request, apiUrl);
    if (path === REFRESH) return refresh(request, apiUrl);
    if (path === LOGOUT) return logout(request, apiUrl);
  }
  return forward(request, apiUrl);
}
