"use client";

import { usePathname, useRouter } from "next/navigation";
import { createContext, use, useCallback, useEffect, useMemo, useState } from "react";

import { api, unwrap } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { onApiEvent } from "@/lib/api/events";
import type { User } from "@/lib/api/types";

/**
 * The signed-in user, loaded from GET /api/v1/me/ for the pages behind sign-in.
 */

export type SessionState =
  | { status: "loading" }
  | { status: "signed-in"; user: User }
  | { status: "signed-out" }
  | { status: "error"; error: ApiError };

type SessionContextValue = {
  state: SessionState;
  /** Load /me again, e.g. after choosing a role or saving the profile. */
  reload: () => Promise<User | null>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | null>(null);

function loginUrl(pathname: string): string {
  return `/login?next=${encodeURIComponent(pathname)}`;
}

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const [state, setState] = useState<SessionState>({ status: "loading" });

  const reload = useCallback(async (): Promise<User | null> => {
    try {
      const user = await unwrap(api.GET("/api/v1/me/"));
      setState({ status: "signed-in", user });
      return user;
    } catch (error) {
      const apiError =
        error instanceof ApiError
          ? error
          : new ApiError({ status: 0, code: "unknown", message: "Something went wrong." });
      setState(
        apiError.status === 401 ? { status: "signed-out" } : { status: "error", error: apiError },
      );
      return null;
    }
  }, []);

  const signOut = useCallback(async () => {
    await fetch("/api/v1/auth/logout/", { method: "POST", credentials: "same-origin" }).catch(
      () => undefined,
    );
    setState({ status: "signed-out" });
    router.replace("/login");
  }, [router]);

  useEffect(() => {
    // Loading /me is the point of this provider; the state update is the result.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reload();
  }, [reload]);

  useEffect(
    () =>
      onApiEvent((event) => {
        if (event.type === "session-expired") setState({ status: "signed-out" });
      }),
    [],
  );

  useEffect(() => {
    if (state.status === "signed-out") router.replace(loginUrl(pathname));
  }, [state.status, router, pathname]);

  const value = useMemo(() => ({ state, reload, signOut }), [state, reload, signOut]);
  return <SessionContext value={value}>{children}</SessionContext>;
}

export function useSession(): SessionContextValue {
  const value = use(SessionContext);
  if (!value) throw new Error("useSession must be used inside <SessionProvider>");
  return value;
}
