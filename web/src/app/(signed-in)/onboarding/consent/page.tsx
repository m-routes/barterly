"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Logo } from "@/components/Logo";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { describeError } from "@/lib/api/errors";
import { homeFor } from "@/lib/session/routing";
import { useSession } from "@/lib/session/session";

import { ConsentForm } from "./ConsentForm";

export default function ConsentPage() {
  const router = useRouter();
  const { state, reload } = useSession();
  const done = state.status === "signed-in" && !state.user.needs_consent;

  useEffect(() => {
    if (done && state.status === "signed-in") router.replace(homeFor(state.user));
  }, [done, router, state]);

  let body: React.ReactNode;
  if (state.status === "error") {
    body = (
      <ErrorState
        title="We couldn't load your account"
        description={describeError(state.error)}
        retry={() => void reload()}
      />
    );
  } else if (state.status !== "signed-in" || done) {
    body = <LoadingState label="Loading your account…" />;
  } else {
    body = (
      <div className="auth-card auth-card--wide">
        <h1 className="auth-card__title">Our terms have changed</h1>
        <p className="auth-card__lead">
          Please read and accept the current versions to keep using Barterly.
        </p>
        <ConsentForm
          onAccepted={async () => {
            const fresh = await reload();
            if (fresh) router.replace(homeFor(fresh));
          }}
        />
      </div>
    );
  }

  return (
    <div className="auth-page">
      <header className="auth-page__header">
        <Logo />
      </header>
      <main id="main" className="auth-page__main">
        {body}
      </main>
    </div>
  );
}
