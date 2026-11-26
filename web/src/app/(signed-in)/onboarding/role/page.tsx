"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Logo } from "@/components/Logo";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { useLoad } from "@/lib/hooks/useLoad";
import { homeFor } from "@/lib/session/routing";
import { useSession } from "@/lib/session/session";

import { RoleForm } from "./RoleForm";

export default function ChooseRolePage() {
  const router = useRouter();
  const { state, reload } = useSession();
  // The beta's rules: which roles need an invite code. If this fails, the form still
  // asks for a code when the server says one is needed.
  const { state: rules } = useLoad(() => unwrap(api.GET("/api/v1/beta/")), "beta-rules");
  const inviteRoles = rules.status === "ready" ? rules.data.invite_required_for : [];
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
          inviteRoles={inviteRoles}
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
