import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { errorBody, jsonResponse, vendorUser } from "../../../test/http";

import { api, authFetch, unwrap } from "./client";
import { ApiError } from "./errors";
import { onApiEvent, type ApiEvent } from "./events";

let network: ReturnType<typeof vi.fn>;
let events: ApiEvent[];
let unsubscribe: () => void;

beforeEach(() => {
  network = vi.fn();
  vi.stubGlobal("fetch", network);
  events = [];
  unsubscribe = onApiEvent((e) => events.push(e));
  window.localStorage.clear();
});

afterEach(() => {
  unsubscribe();
  vi.unstubAllGlobals();
});

function urlOf(call: unknown[]): string {
  const input = call[0];
  return input instanceof Request ? new URL(input.url).pathname : String(input);
}

describe("authFetch", () => {
  it("refreshes once and replays the request after a 401", async () => {
    network
      .mockResolvedValueOnce(jsonResponse(401, errorBody("token_not_valid")))
      .mockResolvedValueOnce(new Response(null, { status: 204 })) // refresh
      .mockResolvedValueOnce(jsonResponse(200, vendorUser));

    const response = await authFetch(new Request("http://localhost/api/v1/me/"));

    expect(response.status).toBe(200);
    expect(network.mock.calls.map(urlOf)).toEqual([
      "/api/v1/me/",
      "/api/v1/auth/refresh/",
      "/api/v1/me/",
    ]);
    expect(events).toEqual([]);
  });

  it("replays the body of a POST", async () => {
    network
      .mockResolvedValueOnce(jsonResponse(401, errorBody("token_not_valid")))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))
      .mockResolvedValueOnce(jsonResponse(200, vendorUser));

    await authFetch(
      new Request("http://localhost/api/v1/me/role/", {
        method: "POST",
        body: JSON.stringify({ role: "vendor" }),
      }),
    );
    const replayed = network.mock.calls[2]![0] as Request;
    expect(await replayed.text()).toBe('{"role":"vendor"}');
  });

  it("reports session-expired when the refresh fails", async () => {
    network
      .mockResolvedValueOnce(jsonResponse(401, errorBody("token_not_valid")))
      .mockResolvedValueOnce(jsonResponse(401, errorBody("token_not_valid")));

    const response = await authFetch(new Request("http://localhost/api/v1/me/"));

    expect(response.status).toBe(401);
    expect(events).toEqual([{ type: "session-expired" }]);
  });

  it("shares one refresh between parallel 401s", async () => {
    let refreshes = 0;
    network.mockImplementation(async (input: Request | string) => {
      const path = urlOf([input]);
      if (path === "/api/v1/auth/refresh/") {
        refreshes += 1;
        await new Promise((r) => setTimeout(r, 5));
        return new Response(null, { status: 204 });
      }
      // First attempt of each call is a 401; the replay succeeds.
      return refreshes === 0
        ? jsonResponse(401, errorBody("token_not_valid"))
        : jsonResponse(200, {});
    });

    const results = await Promise.all([
      authFetch(new Request("http://localhost/api/v1/me/")),
      authFetch(new Request("http://localhost/api/v1/profiles/vendor/me/")),
    ]);

    expect(results.map((r) => r.status)).toEqual([200, 200]);
    expect(refreshes).toBe(1);
  });

  it("doesn't try to refresh after a 401 from an auth endpoint", async () => {
    network.mockResolvedValueOnce(jsonResponse(401, errorBody("invalid_sign_in_token")));
    await authFetch(new Request("http://localhost/api/v1/auth/exchange/", { method: "POST" }));
    expect(network).toHaveBeenCalledTimes(1);
  });
});

describe("api client and unwrap", () => {
  it("returns typed data on success", async () => {
    network.mockResolvedValueOnce(jsonResponse(200, vendorUser));
    const me = await unwrap(api.GET("/api/v1/me/"));
    expect(me.role).toBe("vendor");
  });

  it("throws an ApiError with the API's code, details and request id", async () => {
    network.mockResolvedValueOnce(
      jsonResponse(400, errorBody("validation_error", "Invalid input.", { city: ["Required."] }), {
        "x-request-id": "req-9",
      }),
    );
    const error = await unwrap(
      api.PATCH("/api/v1/profiles/vendor/me/", { body: { city: "" } }),
    ).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 400,
      code: "validation_error",
      details: { city: ["Required."] },
      requestId: "req-9",
    });
    // Validation errors belong to the form, not the global handler.
    expect(events).toEqual([]);
  });

  it("sends server errors to the global handler", async () => {
    network.mockResolvedValueOnce(jsonResponse(500, errorBody("server_error", "Broke.")));
    await unwrap(api.GET("/api/v1/me/")).catch(() => undefined);
    expect(events).toHaveLength(1);
    expect(events[0]).toMatchObject({
      type: "error",
      error: { status: 500, code: "server_error" },
    });
  });

  it("turns a network failure into a network_error ApiError and reports it", async () => {
    network.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const error = await unwrap(api.GET("/api/v1/me/")).catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 0, code: "network_error" });
    expect(events[0]).toMatchObject({ type: "error", error: { code: "network_error" } });
  });
});
