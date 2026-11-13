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
};

/** The Firebase web config, or null when sign-in isn't set up for this environment. */
export function firebaseWebConfig(): FirebaseWebConfig | null {
  const apiKey = process.env.FIREBASE_WEB_API_KEY?.trim();
  const projectId = process.env.FIREBASE_PROJECT_ID?.trim();
  const appId = process.env.FIREBASE_WEB_APP_ID?.trim();
  if (!apiKey || !projectId || !appId) return null;
  const authDomain = process.env.FIREBASE_AUTH_DOMAIN?.trim() || `${projectId}.firebaseapp.com`;
  return { apiKey, authDomain, projectId, appId };
}
