"use client";

import Link from "next/link";

import { LegalFooter } from "@/components/legal/LegalFooter";
import { Logo } from "@/components/Logo";
import { PrivacySettings } from "@/components/privacy/PrivacySettings";
import { LoadingState } from "@/components/ui/states";
import { useSession } from "@/lib/session/session";

/** Privacy settings for anyone signed in (talent included), outside the vendor console. */
export default function AccountPrivacyPage() {
  const { state } = useSession();
  return (
    <div className="legal">
      <header className="landing__header">
        <Link href="/start" aria-label="Barterly home">
          <Logo />
        </Link>
      </header>
      <main id="main" className="legal__main">
        {state.status === "signed-in" ? (
          <PrivacySettings />
        ) : (
          <LoadingState label="Loading your account…" />
        )}
      </main>
      <LegalFooter />
    </div>
  );
}
