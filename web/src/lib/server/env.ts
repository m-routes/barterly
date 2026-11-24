import "server-only";

/**
 * Runtime configuration, read from process.env on the server at request time.
 *
 * Nothing here is baked in at build time (no NEXT_PUBLIC_*), so one image can be
 * promoted from staging to production (see web/Dockerfile).
 */

const LOCAL_API_URL = "http://localhost:8000";

/** Base URL of the Django API, without a trailing slash or /api suffix. */
export function apiUrl(): string {
  const value = process.env.API_URL?.trim() || LOCAL_API_URL;
  return value.replace(/\/+$/, "");
}

/** Public Firebase web config. Not secret, but differs per environment. */
export type FirebaseWebConfig = {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
  /** See lib/firebase/phoneAuth.ts. */
  testNumbersOnly?: boolean;
  localFake?: boolean;
};

/**
 * The acceptance suite's local stack signs in without Firebase (see phoneAuth.ts). Only
 * with BARTERLY_ENV unset or "local" and LOCAL_FAKE_SIGN_IN=1: a deployed web always
 * has BARTERLY_ENV set to staging or production (Terraform).
 */
export function localFakeSignIn(): boolean {
  const env = process.env.BARTERLY_ENV?.trim() || "local";
  return env === "local" && process.env.LOCAL_FAKE_SIGN_IN?.trim() === "1";
}

/**
 * Whether this sign-in may use Firebase test phone numbers only (no reCAPTCHA), for the
 * acceptance suite. Needs FIREBASE_TEST_NUMBERS_ALLOWED=1 on the server (staging) and
 * `?test_numbers=1` on the page; production refuses it whatever the variables say.
 */
export function testNumbersAllowed(requested: boolean): boolean {
  if (!requested) return false;
  if (process.env.BARTERLY_ENV?.trim() === "production") return false;
  return process.env.FIREBASE_TEST_NUMBERS_ALLOWED?.trim() === "1";
}

/** The Firebase web config, or null when sign-in isn't set up for this environment. */
export function firebaseWebConfig(): FirebaseWebConfig | null {
  if (localFakeSignIn()) {
    return {
      apiKey: "local",
      authDomain: "local",
      projectId: "local",
      appId: "local",
      localFake: true,
    };
  }
  const apiKey = process.env.FIREBASE_WEB_API_KEY?.trim();
  const projectId = process.env.FIREBASE_PROJECT_ID?.trim();
  const appId = process.env.FIREBASE_WEB_APP_ID?.trim();
  if (!apiKey || !projectId || !appId) return null;
  const authDomain = process.env.FIREBASE_AUTH_DOMAIN?.trim() || `${projectId}.firebaseapp.com`;
  return { apiKey, authDomain, projectId, appId };
}
