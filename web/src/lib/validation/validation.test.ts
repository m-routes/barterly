import { describe, expect, it } from "vitest";

import { normalizeIndianMobile, otpSchema, phoneSchema } from "./auth";
import { vendorFormDefaults, vendorProfileSchema } from "./vendorProfile";

describe("normalizeIndianMobile", () => {
  it.each([
    ["9876543210", "+919876543210"],
    ["98765 43210", "+919876543210"],
    ["+91 98765-43210", "+919876543210"],
    ["919876543210", "+919876543210"],
    ["09876543210", "+919876543210"],
  ])("%s → %s", (input, expected) => {
    expect(normalizeIndianMobile(input)).toBe(expected);
  });

  it.each(["5876543210", "987654321", "98765432101", "+1 415 555 0100", "abc"])(
    "rejects %s",
    (input) => {
      expect(normalizeIndianMobile(input)).toBeNull();
    },
  );
});

describe("phone and code", () => {
  it("explains a bad phone number", () => {
    const result = phoneSchema.safeParse({ phone: "12345" });
    expect(result.error?.issues[0]?.message).toBe("Enter a 10-digit Indian mobile number.");
  });

  it("wants exactly six digits", () => {
    expect(otpSchema.safeParse({ code: "123456" }).success).toBe(true);
    expect(otpSchema.safeParse({ code: "12345" }).success).toBe(false);
    expect(otpSchema.safeParse({ code: "12345a" }).success).toBe(false);
  });
});

describe("vendorProfileSchema", () => {
  const valid = {
    ...vendorFormDefaults(),
    business_name: "Zostel Manali",
    business_type: "hostel",
    contact_name: "Asha",
    city: "Manali",
    state: "Himachal Pradesh",
    about: "A hostel in the hills.",
  } as const;

  it("accepts a complete profile with optional fields left blank", () => {
    expect(vendorProfileSchema.parse(valid)).toMatchObject({ business_type: "hostel", gstin: "" });
  });

  it("flags every required field when the form is empty", () => {
    const result = vendorProfileSchema.safeParse(vendorFormDefaults());
    const fields = result.error?.issues.map((i) => i.path[0]);
    expect(fields).toEqual(
      expect.arrayContaining([
        "business_name",
        "business_type",
        "contact_name",
        "city",
        "state",
        "about",
      ]),
    );
    expect(result.error?.issues.find((i) => i.path[0] === "state")?.message).toBe(
      "Choose your state or union territory.",
    );
  });

  it("upper-cases and checks the GSTIN", () => {
    expect(vendorProfileSchema.parse({ ...valid, gstin: "29abcde1234f1z5" }).gstin).toBe(
      "29ABCDE1234F1Z5",
    );
    expect(vendorProfileSchema.safeParse({ ...valid, gstin: "29ABCDE1234F1Y5" }).success).toBe(
      false,
    );
  });

  it("wants a full web address", () => {
    expect(vendorProfileSchema.safeParse({ ...valid, website: "zostel.com" }).success).toBe(false);
    expect(vendorProfileSchema.safeParse({ ...valid, website: "https://zostel.com" }).success).toBe(
      true,
    );
  });

  it("rejects a state that isn't in the API's list", () => {
    expect(vendorProfileSchema.safeParse({ ...valid, state: "Atlantis" }).success).toBe(false);
  });
});
