import { z } from "zod";

import { toDecimalString } from "@/components/map/geo";
import type { Amenity, Property, PropertyType } from "@/lib/api/types";
import { AMENITY_LABELS, PROPERTY_TYPE_LABELS } from "@/lib/vendor/labels";

import { INDIAN_STATES, choice } from "./vendorProfile";

/** Backend settings VERIFICATION_MIN_PROPERTY_PHOTOS and properties.models.MAX_PHOTOS. */
export const MIN_VERIFICATION_PHOTOS = 3;
export const MAX_PROPERTY_PHOTOS = 20;
const MAX_HOUSE_RULES = 20;

const PROPERTY_TYPES = Object.keys(PROPERTY_TYPE_LABELS) as [PropertyType, ...PropertyType[]];
const AMENITIES = Object.keys(AMENITY_LABELS) as [Amenity, ...Amenity[]];

export const propertySchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Enter the property's name.")
    .max(150, "Keep the name under 150 characters."),
  property_type: choice(PROPERTY_TYPES, "Choose the kind of property."),
  address: z
    .string()
    .trim()
    .min(1, "Enter the street address.")
    .max(500, "Keep the address under 500 characters."),
  city: z
    .string()
    .trim()
    .min(1, "Enter the city or town.")
    .max(80, "Keep this under 80 characters."),
  state: choice(INDIAN_STATES, "Choose the state or union territory."),
  pincode: z
    .string()
    .trim()
    .regex(/^([1-9][0-9]{5})?$/, "A PIN code is 6 digits and doesn't start with 0."),
  amenities: z.array(z.enum(AMENITIES)),
  house_rules: z
    .string()
    .transform((text) =>
      text
        .split("\n")
        .map((line) => line.trim())
        .filter(Boolean),
    )
    .refine((rules) => rules.length <= MAX_HOUSE_RULES, `At most ${MAX_HOUSE_RULES} rules.`)
    .refine((rules) => rules.every((r) => r.length <= 200), "Keep each rule under 200 characters."),
  women_friendly: z.boolean(),
  latitude: z.number().nullable(),
  longitude: z.number().nullable(),
  location_confirmed: z.boolean(),
});

export type PropertyValues = z.input<typeof propertySchema>;
export type PropertyParsed = z.output<typeof propertySchema>;

export function propertyDefaults(property: Property | null): PropertyValues {
  return {
    name: property?.name ?? "",
    property_type: property?.property_type ?? "",
    address: property?.address ?? "",
    city: property?.city ?? "",
    state: property?.state ?? "",
    pincode: property?.pincode ?? "",
    amenities: property?.amenities ?? [],
    house_rules: (property?.house_rules ?? []).join("\n"),
    women_friendly: property?.women_friendly ?? false,
    latitude: property?.latitude != null ? Number(property.latitude) : null,
    longitude: property?.longitude != null ? Number(property.longitude) : null,
    location_confirmed: property?.location_confirmed ?? false,
  };
}

/** The request body: coordinates as the API's 6-decimal strings. */
export function propertyPayload(values: PropertyParsed) {
  const { latitude, longitude, ...rest } = values;
  const hasPoint = latitude != null && longitude != null;
  return {
    ...rest,
    latitude: hasPoint ? toDecimalString(latitude) : null,
    longitude: hasPoint ? toDecimalString(longitude) : null,
    location_confirmed: hasPoint && values.location_confirmed,
  };
}

export const PROPERTY_FIELDS = Object.keys(propertySchema.shape) as (keyof PropertyValues)[];

/** What still stands between this property and a verification request. */
export function verificationGaps(property: Property): string[] {
  const gaps: string[] = [];
  if (!property.address.trim()) gaps.push("Add the street address.");
  if (property.latitude == null || !property.location_confirmed) {
    gaps.push("Place the map pin and confirm it.");
  }
  const usable = property.photos.filter(
    (p) => p.status !== "rejected" && p.status !== "quarantined",
  );
  if (usable.length < MIN_VERIFICATION_PHOTOS) {
    gaps.push(`Add at least ${MIN_VERIFICATION_PHOTOS} photos (you have ${usable.length}).`);
  }
  const located = usable.filter((p) => p.latitude != null);
  if (located.length < MIN_VERIFICATION_PHOTOS) {
    gaps.push(
      `At least ${MIN_VERIFICATION_PHOTOS} photos need the location they were taken at ` +
        `(${located.length} do). Take them at the property with location turned on.`,
    );
  }
  return gaps;
}
