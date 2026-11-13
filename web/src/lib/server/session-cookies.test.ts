// @vitest-environment node
import { describe, expect, it } from "vitest";

import { fakeJwt } from "../../../test/http";

import {
  REFRESH_COOKIE,
  clearedCookies,
  secondsUntilExpiry,
  tokenCookies,
} from "./session-cookies";

const NOW = Date.UTC(2026, 10, 13, 12, 0, 0);
const nowSeconds = NOW / 1000;

describe("secondsUntilExpiry", () => {
  it("reads exp from the payload", () => {
    expect(secondsUntilExpiry(fakeJwt(nowSeconds + 600), NOW)).toBe(600);
  });

  it("is never negative", () => {
    expect(secondsUntilExpiry(fakeJwt(nowSeconds - 5), NOW)).toBe(0);
  });

  it("is null for something that isn't a JWT", () => {
    expect(secondsUntilExpiry("nope", NOW)).toBeNull();
    expect(secondsUntilExpiry("a.!!!.c", NOW)).toBeNull();
  });
});

describe("tokenCookies", () => {
  it("makes httpOnly, SameSite=Lax cookies that expire with their tokens", () => {
    const [access, refresh] = tokenCookies(
      { access: fakeJwt(nowSeconds + 900), refresh: fakeJwt(nowSeconds + 86400) },
      true,
      NOW,
    );
    expect(access).toMatchObject({ httpOnly: true, sameSite: "lax", secure: true, maxAge: 900 });
    expect(refresh).toMatchObject({ name: REFRESH_COOKIE, maxAge: 86400 });
  });

  it("falls back to the API's default lifetimes when exp can't be read", () => {
    const [access, refresh] = tokenCookies({ access: "x", refresh: "y" }, false, NOW);
    expect(access?.maxAge).toBe(15 * 60);
    expect(refresh?.maxAge).toBe(30 * 24 * 60 * 60);
  });

  it("clears both", () => {
    expect(clearedCookies(true).map((c) => c.maxAge)).toEqual([0, 0]);
  });
});
