// @vitest-environment node
import { NextRequest } from "next/server";
import { describe, expect, it } from "vitest";

import { REFRESH_COOKIE } from "@/lib/server/session-cookies";

import { proxy } from "./proxy";

function visit(path: string, signedIn: boolean) {
  const headers = signedIn ? { cookie: `${REFRESH_COOKIE}=token` } : undefined;
  return proxy(new NextRequest(`https://web.test${path}`, { headers }));
}

describe("proxy", () => {
  it.each(["/console", "/console/gigs", "/onboarding/vendor", "/start", "/talent"])(
    "sends signed-out visitors of %s to /login with a next link",
    (path) => {
      const response = visit(`${path}?tab=1`, false);
      expect(response.status).toBe(307);
      const location = new URL(response.headers.get("location")!);
      expect(location.pathname).toBe("/login");
      expect(location.searchParams.get("next")).toBe(`${path}?tab=1`);
    },
  );

  it("lets signed-in visitors through", () => {
    expect(visit("/console/gigs", true).headers.get("location")).toBeNull();
  });

  it("sends signed-in visitors of /login on to /start", () => {
    const response = visit("/login", true);
    expect(new URL(response.headers.get("location")!).pathname).toBe("/start");
  });

  it("leaves /login alone when signed out", () => {
    expect(visit("/login", false).headers.get("location")).toBeNull();
  });

  it("doesn't treat look-alike paths as protected", () => {
    expect(visit("/consoles", false).headers.get("location")).toBeNull();
  });
});
