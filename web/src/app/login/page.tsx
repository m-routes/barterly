import type { Metadata } from "next";
import { connection } from "next/server";
import { Suspense } from "react";

import { Logo } from "@/components/Logo";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { firebaseWebConfig, testNumbersAllowed } from "@/lib/server/env";

import { LoginForm } from "./LoginForm";

export const metadata: Metadata = { title: "Sign in · Barterly" };

/** Reads the Firebase config at request time, so one build serves every environment. */
async function ConfiguredLoginForm({ testNumbers }: { testNumbers: boolean }) {
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
  return <LoginForm config={{ ...config, testNumbersOnly: testNumbersAllowed(testNumbers) }} />;
}

async function LoginFormFor({
  searchParams,
}: {
  searchParams: Promise<{ test_numbers?: string }>;
}) {
  const { test_numbers } = await searchParams;
  return <ConfiguredLoginForm testNumbers={test_numbers === "1"} />;
}

export default function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ test_numbers?: string }>;
}) {
  return (
    <div className="auth-page">
      <header className="auth-page__header">
        <Logo />
      </header>
      <main id="main" className="auth-page__main">
        <Suspense fallback={<LoadingState label="Loading sign-in…" />}>
          <LoginFormFor searchParams={searchParams} />
        </Suspense>
      </main>
    </div>
  );
}
