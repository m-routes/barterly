/** Map settings and coordinate helpers shared by the map and its text fallback. */

export type LatLng = { latitude: number; longitude: number };

/**
 * OpenStreetMap's standard tiles. Their tile usage policy requires visible attribution
 * (with a link to the copyright page) and no heavy use; switch to a paid tile host by
 * setting NEXT_PUBLIC_MAP_TILE_URL and NEXT_PUBLIC_MAP_ATTRIBUTION.
 */
export const TILE_URL =
  process.env.NEXT_PUBLIC_MAP_TILE_URL || "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
export const ATTRIBUTION =
  process.env.NEXT_PUBLIC_MAP_ATTRIBUTION ||
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
export const MAX_ZOOM = 19;

/** Where the map opens with no pin yet: all of India. */
export const INDIA_CENTER: LatLng = { latitude: 22.5, longitude: 79 };
export const INDIA_ZOOM = 4;
export const PIN_ZOOM = 16;

/** India's bounding box, the same check the backend makes (verification/validators.py). */
const INDIA_BOUNDS = { south: 6, north: 37.6, west: 68, east: 97.5 };

export function isInIndia({ latitude, longitude }: LatLng): boolean {
  return (
    latitude >= INDIA_BOUNDS.south &&
    latitude <= INDIA_BOUNDS.north &&
    longitude >= INDIA_BOUNDS.west &&
    longitude <= INDIA_BOUNDS.east
  );
}

/** The API stores 6 decimal places (about 10 cm). */
export function toDecimalString(value: number): string {
  return value.toFixed(6);
}

export function fromDecimalStrings(
  latitude: string | null | undefined,
  longitude: string | null | undefined,
): LatLng | null {
  if (latitude == null || longitude == null || latitude === "" || longitude === "") return null;
  const point = { latitude: Number(latitude), longitude: Number(longitude) };
  return Number.isFinite(point.latitude) && Number.isFinite(point.longitude) ? point : null;
}

/** "15.552700, 73.751700" style text, for the fallback and for screen readers. */
export function formatPoint({ latitude, longitude }: LatLng): string {
  return `${latitude.toFixed(6)}, ${longitude.toFixed(6)}`;
}

/** Parse a typed coordinate; null when it isn't a number in range. */
export function parseCoordinate(text: string, kind: "latitude" | "longitude"): number | null {
  const trimmed = text.trim();
  if (!/^-?\d{1,3}(\.\d+)?$/.test(trimmed)) return null;
  const value = Number(trimmed);
  const limit = kind === "latitude" ? 90 : 180;
  return Math.abs(value) <= limit ? value : null;
}
