"use client";

import { useCallback, useEffect, useState } from "react";

import { api, unwrap } from "@/lib/api/client";

const EVERY_MS = 60_000;

/** The unread notification count, checked every minute and on demand. */
export function useUnreadCount() {
  const [unread, setUnread] = useState(0);
  const check = useCallback(async () => {
    try {
      const { unread } = await unwrap(api.GET("/api/v1/notifications/unread-count/"));
      setUnread(unread);
    } catch {
      // A missed count isn't worth an error on every page.
    }
  }, []);
  useEffect(() => {
    // Fetching is this effect's job; its result is state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void check();
    const timer = window.setInterval(() => void check(), EVERY_MS);
    return () => window.clearInterval(timer);
  }, [check]);
  return { unread, refresh: check };
}
