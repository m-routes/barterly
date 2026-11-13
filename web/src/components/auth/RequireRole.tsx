"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { describeError } from "@/lib/api/errors";
import type { Role, User } from "@/lib/api/types";
import { accessFor, homeFor } from "@/lib/session/routing";
import { useSession } from "@/lib/session/session";

const FORBIDDEN_COPY: Record<Role, { title: string; description: string }> = {
  vendor: {
    title: "This page is for talent",
    description: "Your account is a vendor account. Your vendor console has everything you need.",
  },
  talent: {
    title: "The web console is for vendors",
    description:
      "Your account is a talent account. Find and apply to gigs in the Barterly app on your phone.",
  },
  admin: {
    title: "Admins use the admin console",
    description: "This console is for vendors. Manage Barterly from the admin console instead.",
  },
};

/**
 * Renders children only for a signed-in user with `role`.
 *
 * Loading → spinner. Signed out → SessionProvider sends them to /login. No role, or
 * an incomplete profile where one is needed → redirect. Another role → an explanation.
 */
export function RequireRole({
  role,
  requireComplete = false,
  children,
}: {
  role: Role;
  requireComplete?: boolean;
  children: (user: User) => React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { state, reload, signOut } = useSession();
  const access =
    state.status === "signed-in" ? accessFor(state.user, role, { requireComplete }) : null;
  const redirectTo = access?.kind === "redirect" ? access.to : null;

  useEffect(() => {
    if (redirectTo) router.replace(redirectTo);
  }, [redirectTo, router]);

  if (state.status === "error") {
    return (
      <ErrorState
        title="We couldn't load your account"
        description={describeError(state.error)}
        retry={() => void reload()}
      />
    );
  }
  if (state.status !== "signed-in" || !access || access.kind === "redirect") {
    return <LoadingState label="Loading your account…" />;
  }
  if (access.kind === "forbidden") {
    const copy = FORBIDDEN_COPY[access.role];
    const home = homeFor(state.user);
    const canGoHome = home !== pathname && access.role !== "admin";
    return (
      <section className="state state--error" aria-labelledby="forbidden-title">
        <h1 id="forbidden-title" className="state__title">
          {copy.title}
        </h1>
        <p className="state__text">{copy.description}</p>
        <div className="state__actions">
          {canGoHome ? <Button onClick={() => router.replace(home)}>Go to my home</Button> : null}
          <Button variant="secondary" onClick={() => void signOut()}>
            Sign out
          </Button>
        </div>
      </section>
    );
  }
  return <>{children(state.user)}</>;
}
