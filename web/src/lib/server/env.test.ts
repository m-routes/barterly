// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));

import { firebaseWebConfig, localFakeSignIn, testNumbersAllowed } from "./env";

describe("testNumbersAllowed", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("needs both the server switch and the page asking for it", () => {
    vi.stubEnv("BARTERLY_ENV", "staging");
    vi.stubEnv("FIREBASE_TEST_NUMBERS_ALLOWED", "1");
    expect(testNumbersAllowed(true)).toBe(true);
    expect(testNumbersAllowed(false)).toBe(false);
    vi.stubEnv("FIREBASE_TEST_NUMBERS_ALLOWED", "");
    expect(testNumbersAllowed(true)).toBe(false);
  });

  it("is never on in production", () => {
    vi.stubEnv("BARTERLY_ENV", "production");
    vi.stubEnv("FIREBASE_TEST_NUMBERS_ALLOWED", "1");
    expect(testNumbersAllowed(true)).toBe(false);
  });
});

describe("localFakeSignIn", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("is only for the local acceptance stack", () => {
    vi.stubEnv("LOCAL_FAKE_SIGN_IN", "1");
    vi.stubEnv("BARTERLY_ENV", "");
    expect(localFakeSignIn()).toBe(true);
    expect(firebaseWebConfig()?.localFake).toBe(true);
    for (const env of ["staging", "production"]) {
      vi.stubEnv("BARTERLY_ENV", env);
      expect(localFakeSignIn()).toBe(false);
    }
    vi.stubEnv("BARTERLY_ENV", "local");
    vi.stubEnv("LOCAL_FAKE_SIGN_IN", "");
    expect(localFakeSignIn()).toBe(false);
  });
});
