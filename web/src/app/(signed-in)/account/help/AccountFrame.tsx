"use client";

import Link from "next/link";

import { LegalFooter } from "@/components/legal/LegalFooter";
import { Logo } from "@/components/Logo";
import { LoadingState } from "@/components/ui/states";
import { useSession } from "@/lib/session/session";

/** Account pages outside the vendor console (talent use these on the web). */
export function AccountFrame({ children }: { children: React.ReactNode }) {
  const { state } = useSession();
  return (
    <div className="legal">
      <header className="landing__header">
        <Link href="/start" aria-label="Barterly home">
          <Logo />
        </Link>
      </header>
      <main id="main" className="legal__main">
        {state.status === "signed-in" ? children : <LoadingState label="Loading your account…" />}
      </main>
      <LegalFooter />
    </div>
  );
}
