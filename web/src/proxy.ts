import { NextResponse, type NextRequest } from "next/server";

import { REFRESH_COOKIE } from "@/lib/server/session-cookies";

/**
 * Fast redirects based only on whether a session cookie exists.
 *
 * Role checks happen in the pages (RequireRole), and the API authorizes every call,
 * so this is a convenience, not the security boundary.
 */

const PROTECTED_PREFIXES = ["/console", "/onboarding", "/start", "/talent"];

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

export function proxy(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const signedIn = Boolean(request.cookies.get(REFRESH_COOKIE)?.value);

  if (!signedIn && isProtected(pathname)) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }
  if (signedIn && pathname === "/login") {
    return NextResponse.redirect(new URL("/start", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/login", "/start", "/talent/:path*", "/console/:path*", "/onboarding/:path*"],
};
