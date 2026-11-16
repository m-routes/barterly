"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/StatusChip";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { AppNotification } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

import { consolePath } from "./links";

/** Everything Barterly told you, newest first. Opening one marks it read. */
export function NotificationInbox() {
  const router = useRouter();
  const { state, reload, setData } = useLoad(
    () => unwrap(api.GET("/api/v1/notifications/", { params: { query: { page_size: 50 } } })),
    "notifications",
  );
  const [busy, setBusy] = useState(false);

  async function open(item: AppNotification) {
    if (!item.read) {
      try {
        await unwrap(
          api.POST("/api/v1/notifications/{notification_id}/read/", {
            params: { path: { notification_id: item.id } },
            body: { from_push: false },
          }),
        );
      } catch {
        // Reading it matters more than marking it.
      }
    }
    const path = consolePath(item.web_url);
    if (path) router.push(path);
    else void reload();
  }

  async function readAll() {
    setBusy(true);
    try {
      await unwrap(api.POST("/api/v1/notifications/read-all/"));
      setData((page) => ({
        ...page,
        results: page.results.map((n) => ({ ...n, read: true })),
      }));
    } finally {
      setBusy(false);
    }
  }

  const unread = state.status === "ready" ? state.data.results.filter((n) => !n.read).length : 0;
  return (
    <div className="page page--narrow">
      <header className="page__header">
        <div className="page__title-row">
          <h1 className="page__title">Notifications</h1>
          <Link href="/console/notifications/settings" className="button button--ghost">
            Settings
          </Link>
        </div>
        <p className="page__lead">New applicants, interviews, agreements, bookings and messages.</p>
      </header>
      {state.status === "loading" ? <LoadingState label="Loading notifications…" /> : null}
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load your notifications"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : null}
      {state.status === "ready" && state.data.results.length === 0 ? (
        <EmptyState
          title="Nothing yet"
          description="When someone applies, signs or messages you, you'll see it here."
        />
      ) : null}
      {state.status === "ready" && state.data.results.length ? (
        <>
          {unread ? (
            <div className="actions-row actions-row--start">
              <Button variant="secondary" busy={busy} onClick={() => void readAll()}>
                Mark all {unread} read
              </Button>
            </div>
          ) : null}
          <ul className="notification-list">
            {state.data.results.map((item) => (
              <li key={item.id}>
                <button
                  type="button"
                  className={`notification${item.read ? "" : " notification--unread"}`}
                  onClick={() => void open(item)}
                >
                  <span className="notification__title">
                    {item.title}
                    {item.read ? null : <span className="visually-hidden"> (unread)</span>}
                  </span>
                  <span className="notification__body">{item.body}</span>
                  <span className="notification__meta">
                    {formatDate(item.created_at)}
                    {item.urgent ? <Chip tone="warning">Urgent</Chip> : null}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
