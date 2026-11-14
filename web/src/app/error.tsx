"use client";

import { ErrorState } from "@/components/ui/states";

export default function RootError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main id="main" className="page-center">
      <ErrorState
        title="Something went wrong"
        description="This page hit a problem. Try again, or go back to the home page."
        retry={reset}
        action={{ label: "Home", href: "/" }}
      />
    </main>
  );
}
