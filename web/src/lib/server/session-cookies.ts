/**
 * The API's JWTs live in httpOnly cookies set by this server, so browser code never
 * holds a token. The BFF route (src/app/api/v1/[...path]/route.ts) moves them between
 * the cookies and the Authorization header.
 *
 * Kept free of Next.js server-only imports so proxy.ts can share the names.
 */

export const ACCESS_COOKIE = "barterly_access";
export const REFRESH_COOKIE = "barterly_refresh";

const FALLBACK_ACCESS_SECONDS = 15 * 60;
const FALLBACK_REFRESH_SECONDS = 30 * 24 * 60 * 60;

export type CookieSpec = {
  name: string;
  value: string;
  httpOnly: true;
  secure: boolean;
  sameSite: "lax";
  path: "/";
  maxAge: number;
};

/**
 * Seconds until the JWT's `exp`, read without verifying the signature.
 *
 * Only used to make the cookie expire with the token; the API verifies every token.
 */
export function secondsUntilExpiry(jwt: string, now: number = Date.now()): number | null {
  const payload = jwt.split(".")[1];
  if (!payload) return null;
  try {
    const json = JSON.parse(Buffer.from(payload, "base64url").toString("utf8")) as {
      exp?: unknown;
    };
    if (typeof json.exp !== "number") return null;
    return Math.max(0, Math.floor(json.exp - now / 1000));
  } catch {
    return null;
  }
}

function cookie(name: string, value: string, maxAge: number, secure: boolean): CookieSpec {
  return { name, value, httpOnly: true, secure, sameSite: "lax", path: "/", maxAge };
}

export function tokenCookies(
  tokens: { access: string; refresh: string },
  secure: boolean,
  now: number = Date.now(),
): CookieSpec[] {
  return [
    cookie(
      ACCESS_COOKIE,
      tokens.access,
      secondsUntilExpiry(tokens.access, now) ?? FALLBACK_ACCESS_SECONDS,
      secure,
    ),
    cookie(
      REFRESH_COOKIE,
      tokens.refresh,
      secondsUntilExpiry(tokens.refresh, now) ?? FALLBACK_REFRESH_SECONDS,
      secure,
    ),
  ];
}

export function clearedCookies(secure: boolean): CookieSpec[] {
  return [cookie(ACCESS_COOKIE, "", 0, secure), cookie(REFRESH_COOKIE, "", 0, secure)];
}
