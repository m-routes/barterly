// @vitest-environment node
import { describe, expect, it } from "vitest";

import { DATA_COLLECTION, scrub, scrubEvent, scrubText } from "./scrub";

describe("scrubText", () => {
  it.each([
    "+91 98765 43210",
    "9876543210",
    "asha@example.com",
    "asha.k@okaxis",
    "ABCDE1234F",
    "1234 5678 9012",
    "50100123456789",
    "eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiIxMjMifQ.c2lnbmF0dXJl",
  ])("masks %s", (secret) => {
    expect(scrubText(`value=${secret} end`)).not.toContain(secret);
  });

  it.each(["booking 3f2a9c1e-0b7d-4a1e-9c3e-1f2d3e4c5b6a", "took 1234 ms", "2026-11-21"])(
    "keeps %s",
    (safe) => {
      expect(scrubText(safe)).toBe(safe);
    },
  );
});

describe("scrub", () => {
  it("drops values under sensitive keys", () => {
    expect(scrub({ phone: "x", nested: { emergency_contact: { name: "R" } }, ok: 1 })).toEqual({
      phone: "[redacted]",
      nested: { emergency_contact: "[redacted]" },
      ok: 1,
    });
  });
});

describe("scrubEvent", () => {
  it("keeps the user id only and drops request bodies and cookies", () => {
    const out = scrubEvent({
      message: "failed for 9876543210",
      user: { id: "u1", email: "a@b.co", ip_address: "1.2.3.4" },
      request: { url: "/x", cookies: "s=1", data: { otp: "1" }, query_string: "phone=1" },
    });
    expect(out.user).toEqual({ id: "u1" });
    expect(out.request).toEqual({ url: "/x", query_string: "[redacted]" });
    expect(JSON.stringify(out)).not.toContain("9876543210");
  });
});

describe("DATA_COLLECTION", () => {
  it("turns off every kind of personal data Sentry would collect", () => {
    expect(DATA_COLLECTION).toMatchObject({
      userInfo: false,
      cookies: false,
      httpHeaders: false,
      httpBodies: [],
      urlQueryParams: false,
    });
  });
});
