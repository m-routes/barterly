"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ErrorState, LoadingState } from "@/components/ui/states";
import { describeError } from "@/lib/api/errors";
import { homeFor } from "@/lib/session/routing";
import { useSession } from "@/lib/session/session";

/** Sends a signed-in person to the right place: role choice, profile setup or console. */
export default function StartPage() {
  const router = useRouter();
  const { state, reload } = useSession();
  const destination = state.status === "signed-in" ? homeFor(state.user) : null;

  useEffect(() => {
    if (destination) router.replace(destination);
  }, [destination, router]);

  return (
    <main id="main" className="page-center">
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load your account"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : (
        <LoadingState label="Signing you in…" />
      )}
    </main>
  );
}
