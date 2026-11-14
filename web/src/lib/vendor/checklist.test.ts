import { describe, expect, it } from "vitest";

import { photo, property, vendorProfile, verification } from "../../../test/fixtures";

import { buildChecklist, checkStatus } from "./checklist";

const located = () => [photo(), photo(), photo()];

function done(input: Parameters<typeof buildChecklist>[0]) {
  return Object.fromEntries(buildChecklist(input).map((s) => [s.id, s.done]));
}

describe("buildChecklist", () => {
  it("starts with nothing done and points at the first steps", () => {
    const steps = buildChecklist({ profile: null, properties: [], verification });
    expect(steps.map((s) => s.done)).toEqual([false, false, false, false, false]);
    expect(steps[0]).toMatchObject({ href: "/onboarding/vendor", action: "Add details" });
    expect(steps[1]).toMatchObject({ href: "/console/properties/new", action: "Add a property" });
  });

  it("needs a confirmed pin, and photos with a location", () => {
    const unpinned = { ...property, location_confirmed: false, photos: [photo(), photo()] };
    expect(done({ profile: vendorProfile, properties: [unpinned], verification })).toMatchObject({
      business: true,
      property: false,
      photos: false,
    });
    const noGps = [photo({ latitude: null, longitude: null }), photo(), photo()];
    expect(
      done({ profile: vendorProfile, properties: [{ ...property, photos: noGps }], verification }),
    ).toMatchObject({ property: true, photos: false });
    expect(
      done({
        profile: vendorProfile,
        properties: [{ ...property, photos: located() }],
        verification,
      }),
    ).toMatchObject({ photos: true });
  });

  it("counts the ID check as started once it has a case, and verified with both badges", () => {
    const started = {
      ...verification,
      checks: verification.checks.map((c) =>
        c.check_type === "id_selfie"
          ? {
              ...c,
              cases: [{ status: "submitted", submitted_at: "2026-11-10T00:00:00Z" } as never],
            }
          : c,
      ),
    };
    const verifiedProperty = {
      ...property,
      photos: located(),
      verification_status: "approved" as const,
    };
    expect(
      done({ profile: vendorProfile, properties: [verifiedProperty], verification: started }),
    ).toMatchObject({
      kyc: true,
      verified: false,
    });
    const withBadge = {
      ...started,
      badges: [{ kind: "id_verified" as const, granted_at: "", grant_reason: "", case_id: null }],
    };
    expect(
      Object.values(
        done({ profile: vendorProfile, properties: [verifiedProperty], verification: withBadge }),
      ),
    ).toEqual([true, true, true, true, true]);
  });
});

describe("checkStatus", () => {
  it("uses the newest case", () => {
    const check = {
      ...verification.checks[0]!,
      cases: [
        {
          status: "rejected",
          submitted_at: "2026-10-01T00:00:00Z",
          reviewed_at: "2026-10-02T00:00:00Z",
        },
        { status: "submitted", submitted_at: "2026-11-01T00:00:00Z", reviewed_at: null },
      ] as never[],
    };
    expect(checkStatus(check)).toBe("submitted");
    expect(checkStatus(undefined)).toBe("not_started");
  });
});
