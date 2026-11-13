"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Logo } from "@/components/Logo";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { describeError } from "@/lib/api/errors";
import { homeFor } from "@/lib/session/routing";
import { useSession } from "@/lib/session/session";

import { RoleForm } from "./RoleForm";

export default function ChooseRolePage() {
  const router = useRouter();
  const { state, reload } = useSession();
  // Anyone who already has a role belongs elsewhere.
  const elsewhere = state.status === "signed-in" && state.user.role ? homeFor(state.user) : null;

  useEffect(() => {
    if (elsewhere) router.replace(elsewhere);
  }, [elsewhere, router]);

  let body: React.ReactNode;
  if (state.status === "error") {
    body = (
      <ErrorState
        title="We couldn't load your account"
        description={describeError(state.error)}
        retry={() => void reload()}
      />
    );
  } else if (state.status !== "signed-in" || elsewhere) {
    body = <LoadingState label="Loading your account…" />;
  } else {
    body = (
      <div className="auth-card auth-card--wide">
        <h1 className="auth-card__title">How will you use Barterly?</h1>
        <RoleForm
          onChosen={async (user) => {
            const fresh = (await reload()) ?? user;
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
