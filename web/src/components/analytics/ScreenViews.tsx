"use client";

import { usePathname } from "next/navigation";
import { useEffect } from "react";

import { screenOf } from "@/lib/analytics/events";
import { track } from "@/lib/analytics/track";

/** One screen_view per page, by its route with the ids taken out. Sent only with consent. */
export function ScreenViews() {
  const pathname = usePathname();
  useEffect(() => {
    if (pathname) track("screen_view", { screen: screenOf(pathname) });
  }, [pathname]);
  return null;
}
