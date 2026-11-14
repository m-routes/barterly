"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { RequireRole } from "@/components/auth/RequireRole";
import { Logo } from "@/components/Logo";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, describeError } from "@/lib/api/errors";
import type { VendorProfile } from "@/lib/api/types";
import { useSession } from "@/lib/session/session";

import { VendorProfileForm } from "./VendorProfileForm";

type Load =
  | { status: "loading" }
  | { status: "ready"; profile: VendorProfile | null }
  | { status: "error"; error: unknown };

function ProfileSetup() {
  const router = useRouter();
  const { reload } = useSession();
  const [load, setLoad] = useState<Load>({ status: "loading" });

  const fetchProfile = useCallback(async () => {
    setLoad({ status: "loading" });
    try {
      const profile = await unwrap(api.GET("/api/v1/profiles/vendor/me/"));
      setLoad({ status: "ready", profile });
    } catch (error) {
      if (error instanceof ApiError && error.code === "profile_not_found") {
        setLoad({ status: "ready", profile: null });
      } else {
        setLoad({ status: "error", error });
      }
    }
  }, []);

  useEffect(() => {
    // Loading the profile is this effect's job; its result is state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void fetchProfile();
  }, [fetchProfile]);

  if (load.status === "loading") return <LoadingState label="Loading your profile…" />;
  if (load.status === "error") {
    return (
      <ErrorState
        title="We couldn't load your profile"
        description={describeError(load.error)}
        retry={() => void fetchProfile()}
      />
    );
  }
  return (
    <VendorProfileForm
      initial={load.profile}
      onSaved={async (profile) => {
        if (!profile.profile_complete) return;
        await reload();
        router.replace("/console");
      }}
    />
  );
}

export default function VendorOnboardingPage() {
  return (
    <div className="auth-page">
      <header className="auth-page__header">
        <Logo />
      </header>
      <main id="main" className="auth-page__main">
        <div className="auth-card auth-card--wide">
          <h1 className="auth-card__title">Set up your business profile</h1>
          <p className="auth-card__lead">
            Talent see this before they apply. You can change it at any time.
          </p>
          <RequireRole role="vendor">{() => <ProfileSetup />}</RequireRole>
        </div>
      </main>
    </div>
  );
}
