"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, unwrap } from "@/lib/api/client";

const EVERY_MS = 60_000;

/** The sidebar's link to the inbox, with the unread count (checked every minute). */
export function NotificationsLink({ onNavigate }: { onNavigate?: () => void }) {
  const [unread, setUnread] = useState(0);
  useEffect(() => {
    let live = true;
    async function check() {
      try {
        const { unread } = await unwrap(api.GET("/api/v1/notifications/unread-count/"));
        if (live) setUnread(unread);
      } catch {
        // A missed count isn't worth an error on every page.
      }
    }
    void check();
    const timer = window.setInterval(() => void check(), EVERY_MS);
    return () => {
      live = false;
      window.clearInterval(timer);
    };
  }, []);
  return (
    <Link href="/console/notifications" className="sidebar__link" onClick={onNavigate}>
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
        <path
          d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2Zm4 4a2 2 0 0 0 4 0"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinejoin="round"
        />
      </svg>
      Notifications
      {unread > 0 ? (
        <span className="badge" aria-label={`${unread} unread`}>
          {unread > 99 ? "99+" : unread}
        </span>
      ) : null}
    </Link>
  );
}
