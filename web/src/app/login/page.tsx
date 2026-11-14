import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Logo } from "@/components/Logo";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { firebaseWebConfig } from "@/lib/server/env";

import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Sign in · Barterly" };

/** Reads the Firebase config at request time, so one build serves every environment. */
async function ConfiguredLoginForm() {
  await connection();
  const config = firebaseWebConfig();
  if (!config) {
    return (
      <ErrorState
        title="Sign-in isn't available"
        description="Phone sign-in hasn't been set up for this site yet. Please try again later."
        action={{ label: "Back to home", href: "/" }}
      />
    );
  }
  return <LoginForm config={config} />;
}

export default function LoginPage() {
  return (
    <div className="auth-page">
      <header className="auth-page__header">
        <Logo />
      </header>
      <main id="main" className="auth-page__main">
        <Suspense fallback={<LoadingState label="Loading sign-in…" />}>
          <ConfiguredLoginForm />
        </Suspense>
      </main>
    </div>
  );
}
