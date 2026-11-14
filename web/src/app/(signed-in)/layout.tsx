import { Suspense } from "react";

import { LoadingState } from "@/components/ui/states";
import { SessionProvider } from "@/lib/session/session";

/**
 * Pages behind sign-in share one session, loaded once from /api/v1/me/.
 *
 * The provider reads the URL, which isn't known when a page with an id in its path
 * (/console/gigs/[gigId]/…) is prerendered, so it streams in behind this boundary.
 * Pages with fixed paths still prerender in full.
 */
export default function SignedInLayout({ children }: { children: React.ReactNode }) {
  return (
    <Suspense fallback={<LoadingState />}>
      <SessionProvider>{children}</SessionProvider>
    </Suspense>
  );
}
