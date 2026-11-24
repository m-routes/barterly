import { NextResponse } from "next/server";
import { connection } from "next/server";

import { sentryConfig } from "@/lib/server/env";

/**
 * The browser's Sentry settings, read at request time so one image serves every
 * environment (pages are prerendered and can't carry them). Events go to /monitoring,
 * a same-origin tunnel to Sentry (next.config.ts), so the CSP needs no change.
 */
export async function GET() {
  await connection();
  const config = sentryConfig();
  return NextResponse.json(config ?? { dsn: null }, {
    headers: { "Cache-Control": "public, max-age=300" },
  });
}
