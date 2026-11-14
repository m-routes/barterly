import { z } from "zod";

import type { BusinessType, IndianState, VendorProfile } from "@/lib/api/types";

/**
 * Labels for the API's enums. Typed as Record<Enum, …>, so a value added to or removed
 * from the OpenAPI schema fails `tsc` until it's listed here.
 */
export const BUSINESS_TYPE_LABELS: Record<BusinessType, string> = {
  hostel: "Hostel",
  homestay: "Homestay",
  guesthouse: "Guesthouse",
  hotel: "Hotel",
  resort: "Resort",
  cafe: "Café",
  restaurant: "Restaurant",
  camp: "Camp",
  farm: "Farm stay",
  tour_operator: "Tour operator",
  coworking: "Co-working / co-living",
  other: "Other",
};

const STATE_SET: Record<IndianState, true> = {
  "Andhra Pradesh": true,
  "Arunachal Pradesh": true,
  Assam: true,
  Bihar: true,
  Chhattisgarh: true,
  Goa: true,
  Gujarat: true,
  Haryana: true,
  "Himachal Pradesh": true,
  Jharkhand: true,
  Karnataka: true,
  Kerala: true,
  "Madhya Pradesh": true,
  Maharashtra: true,
  Manipur: true,
  Meghalaya: true,
  Mizoram: true,
  Nagaland: true,
  Odisha: true,
  Punjab: true,
  Rajasthan: true,
  Sikkim: true,
  "Tamil Nadu": true,
  Telangana: true,
  Tripura: true,
  "Uttar Pradesh": true,
  Uttarakhand: true,
  "West Bengal": true,
  "Andaman and Nicobar Islands": true,
  Chandigarh: true,
  "Dadra and Nagar Haveli and Daman and Diu": true,
  Delhi: true,
  "Jammu and Kashmir": true,
  Ladakh: true,
  Lakshadweep: true,
  Puducherry: true,
};

export const BUSINESS_TYPES = Object.keys(BUSINESS_TYPE_LABELS) as [
  BusinessType,
  ...BusinessType[],
];
export const INDIAN_STATES = Object.keys(STATE_SET) as [IndianState, ...IndianState[]];

const GSTIN = /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$/;

const required = (label: string, max: number) =>
  z.string().trim().min(1, `Enter ${label}.`).max(max, `Keep this under ${max} characters.`);

/** A select that starts blank: "" is allowed in, but fails with `message`. */
export const choice = <T extends string>(values: [T, ...T[]], message: string) =>
  z.union([z.literal(""), z.enum(values)]).transform((value, ctx): T => {
    if (value === "") {
      ctx.addIssue({ code: "custom", message });
      return z.NEVER;
    }
    return value;
  });

export const vendorProfileSchema = z.object({
  business_name: required("your business name", 150),
  business_type: choice(BUSINESS_TYPES, "Choose your business type."),
  contact_name: required("a contact name", 80),
  city: required("your city", 80),
  state: choice(INDIAN_STATES, "Choose your state or union territory."),
  about: required("a few lines about your place", 3000),
  address: z.string().trim().max(500, "Keep this under 500 characters."),
  gstin: z
    .string()
    .trim()
    .toUpperCase()
    .refine((v) => v === "" || GSTIN.test(v), "Enter a valid 15-character GSTIN."),
  website: z
    .string()
    .trim()
    .max(200, "Keep this under 200 characters.")
    .refine((v) => v === "" || /^https?:\/\/[^\s.]+\.[^\s]+$/i.test(v), {
      message: "Enter a full web address, starting with https://",
    }),
});

/** What the form edits (the selects are "" until chosen). */
export type VendorProfileValues = z.input<typeof vendorProfileSchema>;
export type VendorProfilePayload = z.output<typeof vendorProfileSchema>;

export const VENDOR_FIELDS = [
  "business_name",
  "business_type",
  "contact_name",
  "city",
  "state",
  "about",
  "address",
  "gstin",
  "website",
] as const satisfies ReadonlyArray<keyof VendorProfileValues>;

export function vendorFormDefaults(profile?: Partial<VendorProfile> | null): VendorProfileValues {
  return {
    business_name: profile?.business_name ?? "",
    business_type: profile?.business_type ?? "",
    contact_name: profile?.contact_name ?? "",
    city: profile?.city ?? "",
    state: profile?.state ?? "",
    about: profile?.about ?? "",
    address: profile?.address ?? "",
    gstin: profile?.gstin ?? "",
    website: profile?.website ?? "",
  };
}
