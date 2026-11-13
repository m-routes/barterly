import { describe, expect, it } from "vitest";

import { accessFor, homeFor, safeNextPath } from "./routing";

describe("homeFor", () => {
  it.each([
    [{ role: "", profile_complete: false }, "/onboarding/role"],
    [{ role: "vendor", profile_complete: false }, "/onboarding/vendor"],
    [{ role: "vendor", profile_complete: true }, "/console"],
    [{ role: "talent", profile_complete: false }, "/talent"],
    [{ role: "admin", profile_complete: true }, "/console"],
  ] as const)("%o → %s", (user, expected) => {
    expect(homeFor(user)).toBe(expected);
  });
});

describe("accessFor", () => {
  it("sends people without a role to choose one", () => {
    expect(accessFor({ role: "", profile_complete: false }, "vendor")).toEqual({
      kind: "redirect",
      to: "/onboarding/role",
    });
  });

  it("forbids other roles", () => {
    expect(accessFor({ role: "talent", profile_complete: true }, "vendor")).toEqual({
      kind: "forbidden",
      role: "talent",
    });
  });

  it("sends vendors with an incomplete profile to finish it when required", () => {
    const user = { role: "vendor", profile_complete: false } as const;
    expect(accessFor(user, "vendor", { requireComplete: true })).toEqual({
      kind: "redirect",
      to: "/onboarding/vendor",
    });
    expect(accessFor(user, "vendor")).toEqual({ kind: "allow" });
  });
});

describe("safeNextPath", () => {
  it.each(["/console/gigs", "/console?tab=1"])("accepts %s", (next) => {
    expect(safeNextPath(next)).toBe(next);
  });

  it.each([null, "", "https://evil.test", "//evil.test", "/\\evil.test", "/login", "/api/v1/me/"])(
    "rejects %s",
    (next) => {
      expect(safeNextPath(next)).toBeNull();
    },
  );
});
