import { describe, expect, it } from "vitest";

import { codeAt, codeMatches, fromBase32, verifyPass } from "./crypto";

// Made by the backend (apps/attendance/signing.py) with a fixed test key, so these
// tests prove the console verifies exactly what the server signs.
const TOKEN =
  "BRT1.eyJ2IjoxLCJraWQiOiJmZTgxMmMxMmYzYWI0Y2U2IiwiYiI6ImItMSIsInQiOiJ0LTEiLCJwIjoicC0xIiwibmJmIjoxNzk2MDgzMjAwLCJleHAiOjE3OTYyNTYwMDB9.valiraPqQSaDE2Q9x3iNCw9iw9qa_vBCTA1GjYS1eEF2ib5yLcGlsgMEtKXcT_OARQGHuE6o7io4Ort4ZKeoBA";
const KEYS = [
  {
    kid: "fe812c12f3ab4ce6",
    alg: "Ed25519",
    public_key: "6kpsY-KcUgq-9VB7Ey7F-ZVHdq6-vnuSQh7qaRRG0iw",
  },
];
const INSIDE = new Date("2026-12-02T00:00:00Z");

describe("verifyPass", () => {
  it("accepts a pass the server signed", () => {
    const result = verifyPass(TOKEN, KEYS, INSIDE);
    expect(result).toMatchObject({ ok: true, payload: { b: "b-1", t: "t-1", p: "p-1" } });
  });

  it("refuses tampering, unknown keys and junk", () => {
    const [prefix, body, sig] = TOKEN.split(".");
    const forged = btoa(atob(body!.replace(/-/g, "+").replace(/_/g, "/")).replace("b-1", "b-2"))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    expect(verifyPass(`${prefix}.${forged}.${sig}`, KEYS, INSIDE)).toEqual({
      ok: false,
      reason: "bad-signature",
    });
    expect(verifyPass(TOKEN.slice(0, -6) + "AAAAAA", KEYS, INSIDE)).toMatchObject({ ok: false });
    expect(verifyPass(TOKEN, [{ ...KEYS[0]!, kid: "other" }], INSIDE)).toEqual({
      ok: false,
      reason: "unknown-key",
    });
    expect(verifyPass("https://example.com", KEYS, INSIDE)).toEqual({
      ok: false,
      reason: "not-a-pass",
    });
  });

  it("checks the validity window, allowing for clock drift", () => {
    expect(verifyPass(TOKEN, KEYS, new Date("2026-12-04T00:00:00Z"))).toEqual({
      ok: false,
      reason: "expired",
    });
    expect(verifyPass(TOKEN, KEYS, new Date("2026-11-30T23:00:00Z"))).toEqual({
      ok: false,
      reason: "not-yet",
    });
    expect(verifyPass(TOKEN, KEYS, new Date("2026-11-30T23:59:00Z")).ok).toBe(true); // 1 min early
  });
});

describe("codes", () => {
  it("matches the server's code for the same secret and time", () => {
    expect(codeAt("JBSWY3DPEHPK3PXP", new Date("2026-12-01T10:00:00Z"))).toBe("832515");
  });

  it("matches the RFC 6238 SHA-1 vector", () => {
    const secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ";
    expect(codeAt(secret, new Date(300_000))).toBe("287082");
    expect(codeMatches(secret, "287 082", new Date(600_000))).toBe(true); // a step late
    expect(codeMatches(secret, "287082", new Date(900_000))).toBe(false);
  });

  it("decodes base32", () => {
    expect(new TextDecoder().decode(fromBase32("JBSWY3DP"))).toBe("Hello");
  });
});
