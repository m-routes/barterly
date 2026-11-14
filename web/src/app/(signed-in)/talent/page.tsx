"use client";

import { RequireRole } from "@/components/auth/RequireRole";
import { Logo } from "@/components/Logo";
import { Button } from "@/components/ui/Button";
import { useSession } from "@/lib/session/session";

/** Talent use the mobile app; the web is the vendor console. */
function TalentWelcome() {
  const { signOut } = useSession();
  return (
    <div className="auth-card auth-card--wide">
      <h1 className="auth-card__title">Barterly for talent lives in the app</h1>
      <p className="auth-card__lead">
        Your account is set up for talent. Find gigs, apply and chat with hosts in the Barterly app
        on your phone, signed in with this same number.
      </p>
      <Button variant="secondary" onClick={() => void signOut()}>
        Sign out
      </Button>
    </div>
  );
}

export default function TalentPage() {
  return (
    <div className="auth-page">
      <header className="auth-page__header">
        <Logo />
      </header>
      <main id="main" className="auth-page__main">
        <RequireRole role="talent">{() => <TalentWelcome />}</RequireRole>
      </main>
    </div>
  );
}
