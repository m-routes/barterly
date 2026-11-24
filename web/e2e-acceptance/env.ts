import { readFileSync } from "node:fs";
import { join } from "node:path";

/** Where the suite runs, and how personas prove their phone. */
export const WEB_URL = process.env.ACCEPTANCE_WEB_URL ?? "http://localhost:3011";
export const API_URL = process.env.ACCEPTANCE_API_URL ?? "http://localhost:8011";
/** Firebase test number code on staging; the local stack's fake accepts 123456. */
export const OTP_CODE = process.env.E2E_OTP_CODE ?? "123456";
/** The admin persona's back-office password (seed_staging sets it from the same secret). */
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD ?? "";

export type Persona = {
  role: string;
  phone: string;
  name: string;
  business_name?: string;
  business_type?: string;
  property_type?: string;
  city?: string;
  state?: string;
  pincode?: string;
  latitude?: number;
  longitude?: number;
};

const all: Record<string, Persona> = JSON.parse(
  readFileSync(join(__dirname, "../../backend/apps/qa/personas.json"), "utf8"),
);

/** A persona the backend seeds (backend/apps/qa/personas.json). */
export function persona(key: string): Persona {
  const found = all[key];
  if (!found || key.startsWith("_")) throw new Error(`No persona ${key} in personas.json`);
  return found;
}

/** "+919000000101" → "9000000101", as people type it. */
export const national = (phone: string) => phone.replace(/^\+91/, "");

/**
 * What `manage.py prepare_journey --talent <key>` printed for each talent, as
 * <ACCEPTANCE_FIXTURES_DIR>/<key>.json (the nightly workflow and docs/qa/README.md
 * show how they're made).
 */
export function fixturesFor<T = Record<string, string>>(talentKey: string): T {
  const dir = process.env.ACCEPTANCE_FIXTURES_DIR;
  if (!dir) throw new Error("Set ACCEPTANCE_FIXTURES_DIR (prepare_journey output per talent).");
  // Test tooling: the path comes from the CI workflow, never from a request.
  // eslint-disable-next-line security/detect-non-literal-fs-filename
  return JSON.parse(readFileSync(join(dir, `${talentKey}.json`), "utf8")) as T;
}
