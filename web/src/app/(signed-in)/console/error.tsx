"use client";

import { ErrorState } from "@/components/ui/states";

export default function ConsoleError({ reset }: { error: Error; reset: () => void }) {
  return (
    <ErrorState
      title="This page didn't load"
      description="Something went wrong showing this page. Try again, or pick another section."
      retry={reset}
    />
  );
}
