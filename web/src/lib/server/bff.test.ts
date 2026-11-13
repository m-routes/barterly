// @vitest-environment node
import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { errorBody, fakeJwt, jsonResponse } from "../../../test/http";

import { handleApiRequest } from "./bff";
import { ACCESS_COOKIE, REFRESH_COOKIE } from "./session-cookies";

const API = "http://api.test";
const SITE = "https://web.test";

function request(
  path: string,
  init: {
    method?: string;
    body?: unknown;
    cookies?: Record<string, string>;
    origin?: string | null;
  } = {},
) {
  const headers = new Headers({ "content-type": "application/json" });
  if (init.cookies) {
    headers.set(
      "cookie",
      Object.entries(init.cookies)
        .map(([k, v]) => `${k}=${v}`)
        .join("; "),
    );
  }
  const method = init.method ?? "GET";
  if (init.origin !== null && method !== "GET") headers.set("origin", init.origin ?? SITE);
  return new NextRequest(`${SITE}${path}`, {
    method,
    headers,
    body: init.body === undefined ? undefined : JSON.stringify(init.body),
  });
}

let upstream: ReturnType<typeof vi.fn>;

beforeEach(() => {
  upstream = vi.fn();
  vi.stubGlobal("fetch", upstream);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function lastCall(): { url: string; init: RequestInit & { headers: Headers } } {
  const [url, init] = upstream.mock.calls.at(-1) as [string, RequestInit & { headers: Headers }];
  return { url, init };
}

function setCookie(response: Response, name: string) {
  return response.headers
    .getSetCookie()
    .find((c) => c.startsWith(`${name}=`))
    ?.toLowerCase();
}

describe("forwarding", () => {
  it("sends the access cookie as a bearer token, with query string and slash kept", async () => {
    upstream.mockResolvedValue(jsonResponse(200, { ok: true }, { "x-request-id": "req-1" }));
    const response = await handleApiRequest(
      request("/api/v1/profiles/skills/?page=2", { cookies: { [ACCESS_COOKIE]: "acc" } }),
      API,
    );
    const { url, init } = lastCall();
    expect(url).toBe(`${API}/api/v1/profiles/skills/?page=2`);
    expect(init.headers.get("authorization")).toBe("Bearer acc");
    expect(response.status).toBe(200);
    expect(response.headers.get("x-request-id")).toBe("req-1");
    expect(await response.json()).toEqual({ ok: true });
  });

  it("adds the trailing slash Django expects", async () => {
    upstream.mockResolvedValue(jsonResponse(200, {}));
    await handleApiRequest(request("/api/v1/me"), API);
    expect(lastCall().url).toBe(`${API}/api/v1/me/`);
  });

  it("sends no Authorization header without an access cookie", async () => {
    upstream.mockResolvedValue(jsonResponse(401, errorBody("not_authenticated")));
    const response = await handleApiRequest(request("/api/v1/me/"), API);
    expect(lastCall().init.headers.has("authorization")).toBe(false);
    expect(response.status).toBe(401);
  });

  it("forwards bodies of unsafe methods", async () => {
    upstream.mockResolvedValue(jsonResponse(200, { city: "Goa" }));
    await handleApiRequest(
      request("/api/v1/profiles/vendor/me/", { method: "PATCH", body: { city: "Goa" } }),
      API,
    );
    const { init } = lastCall();
    expect(init.method).toBe("PATCH");
    expect(new TextDecoder().decode(init.body as ArrayBuffer)).toBe('{"city":"Goa"}');
  });

  it("rejects unsafe requests from another origin", async () => {
    const response = await handleApiRequest(
      request("/api/v1/me/role/", { method: "POST", body: {}, origin: "https://evil.test" }),
      API,
    );
    expect(response.status).toBe(403);
    expect((await response.json()).code).toBe("cross_origin");
    expect(upstream).not.toHaveBeenCalled();
  });

  it("returns 502 api_unavailable when the API can't be reached", async () => {
    upstream.mockRejectedValue(new TypeError("fetch failed"));
    const response = await handleApiRequest(request("/api/v1/me/"), API);
    expect(response.status).toBe(502);
    expect((await response.json()).code).toBe("api_unavailable");
  });
});

describe("auth endpoints", () => {
  const access = fakeJwt(Math.floor(Date.now() / 1000) + 900);
  const refresh = fakeJwt(Math.floor(Date.now() / 1000) + 30 * 86400);

  it("exchange stores the tokens in httpOnly cookies and strips them from the body", async () => {
    upstream.mockResolvedValue(
      jsonResponse(200, {
        access,
        refresh,
        is_new_user: true,
        needs_role: true,
        user: { id: "u1" },
      }),
    );
    const response = await handleApiRequest(
      request("/api/v1/auth/exchange/", { method: "POST", body: { id_token: "firebase" } }),
      API,
    );
    expect(response.status).toBe(200);
    const body = await response.json();
    expect(body).toEqual({ is_new_user: true, needs_role: true, user: { id: "u1" } });
    const accessCookie = setCookie(response, ACCESS_COOKIE)!;
    expect(accessCookie).toContain("httponly");
    expect(accessCookie).toContain("secure");
    expect(accessCookie).toContain("samesite=lax");
    expect(accessCookie).toMatch(/max-age=(89\d|900)/);
    expect(setCookie(response, REFRESH_COOKIE)).toContain("httponly");
  });

  it("exchange passes API errors through and sets no cookies", async () => {
    upstream.mockResolvedValue(jsonResponse(401, errorBody("invalid_sign_in_token")));
    const response = await handleApiRequest(
      request("/api/v1/auth/exchange/", { method: "POST", body: { id_token: "bad" } }),
      API,
    );
    expect(response.status).toBe(401);
    expect(response.headers.getSetCookie()).toEqual([]);
  });

  it("refresh sends the refresh cookie, rotates both cookies and returns no tokens", async () => {
    upstream.mockResolvedValue(jsonResponse(200, { access, refresh }));
    const response = await handleApiRequest(
      request("/api/v1/auth/refresh/", { method: "POST", cookies: { [REFRESH_COOKIE]: "old" } }),
      API,
    );
    expect(JSON.parse(lastCall().init.body as string)).toEqual({ refresh: "old" });
    expect(response.status).toBe(204);
    expect(setCookie(response, ACCESS_COOKIE)).toContain(access.toLowerCase());
    expect(setCookie(response, REFRESH_COOKIE)).toContain(refresh.toLowerCase());
  });

  it("refresh without a cookie is 401 and doesn't call the API", async () => {
    const response = await handleApiRequest(
      request("/api/v1/auth/refresh/", { method: "POST" }),
      API,
    );
    expect(response.status).toBe(401);
    expect(upstream).not.toHaveBeenCalled();
  });

  it("a rejected refresh clears both cookies", async () => {
    upstream.mockResolvedValue(jsonResponse(401, errorBody("token_not_valid")));
    const response = await handleApiRequest(
      request("/api/v1/auth/refresh/", { method: "POST", cookies: { [REFRESH_COOKIE]: "spent" } }),
      API,
    );
    expect(response.status).toBe(401);
    expect(setCookie(response, ACCESS_COOKIE)).toContain("max-age=0");
    expect(setCookie(response, REFRESH_COOKIE)).toContain("max-age=0");
  });

  it("logout blacklists the refresh token and clears cookies even if the API fails", async () => {
    upstream.mockRejectedValue(new TypeError("down"));
    const response = await handleApiRequest(
      request("/api/v1/auth/logout/", {
        method: "POST",
        cookies: { [ACCESS_COOKIE]: "acc", [REFRESH_COOKIE]: "ref" },
      }),
      API,
    );
    const { init } = lastCall();
    expect(JSON.parse(init.body as string)).toEqual({ refresh: "ref" });
    expect(init.headers.get("authorization")).toBe("Bearer acc");
    expect(response.status).toBe(204);
    expect(setCookie(response, REFRESH_COOKIE)).toContain("max-age=0");
  });
});
