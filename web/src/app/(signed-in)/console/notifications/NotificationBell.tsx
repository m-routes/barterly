"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { AppNotification } from "@/lib/api/types";
import { formatDate } from "@/lib/format";

import { consolePath } from "./links";

/**
 * The bell: the unread count, and the latest few notifications in a popover. Opening
 * one marks it read and goes where it points; "See all" opens the inbox.
 */
export function NotificationBell({ unread, onRead }: { unread: number; onRead: () => void }) {
  const ids = useId();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<AppNotification[] | null>(null);
  const [error, setError] = useState("");
  const root = useRef<HTMLDivElement>(null);
  const button = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    let live = true;
    unwrap(api.GET("/api/v1/notifications/", { params: { query: { page_size: 6 } } }))
      .then((page) => live && setItems(page.results))
      .catch((err: unknown) => live && setError(describeError(err)));
    const onDown = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => {
      live = false;
      document.removeEventListener("mousedown", onDown);
    };
  }, [open]);

  async function pick(item: AppNotification) {
    setOpen(false);
    if (!item.read) {
      setItems((list) => list?.map((n) => (n.id === item.id ? { ...n, read: true } : n)) ?? null);
      try {
        await unwrap(
          api.POST("/api/v1/notifications/{notification_id}/read/", {
            params: { path: { notification_id: item.id } },
            body: { from_push: false },
          }),
        );
      } catch {
        // Opening it matters more than the read mark.
      }
      onRead();
    }
    const path = consolePath(item.web_url);
    router.push(path ?? "/console/notifications");
  }

  return (
    <div
      ref={root}
      className="bell"
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          setOpen(false);
          button.current?.focus();
        }
      }}
    >
      <button
        ref={button}
        type="button"
        className="bell__button"
        aria-expanded={open}
        aria-controls={`${ids}-popover`}
        onClick={() => {
          setItems(null);
          setError("");
          setOpen((o) => !o);
        }}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" focusable="false">
          <path
            d="M6 8a6 6 0 0 1 12 0c0 7 3 8 3 8H3s3-1 3-8M10 20a2 2 0 0 0 4 0"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="visually-hidden">Notifications{unread ? `, ${unread} unread` : ""}</span>
        {unread > 0 ? (
          <span className="bell__count" aria-hidden="true">
            {unread > 99 ? "99+" : unread}
          </span>
        ) : null}
      </button>
      {open ? (
        <div
          id={`${ids}-popover`}
          className="bell__popover"
          role="region"
          aria-label="Latest notifications"
        >
          {items === null && !error ? <LoadingState label="Loading…" /> : null}
          {error ? <p className="field__error">{error}</p> : null}
          {items && items.length === 0 ? <p className="field__hint">Nothing yet.</p> : null}
          {items && items.length ? (
            <ul className="bell__list">
              {items.map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`bell__item${item.read ? "" : " bell__item--unread"}`}
                    onClick={() => void pick(item)}
                  >
                    <span className="bell__title">
                      {item.title}
                      {item.read ? null : <span className="visually-hidden"> (unread)</span>}
                    </span>
                    <span className="bell__body">{item.body}</span>
                    <span className="bell__when">{formatDate(item.created_at)}</span>
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          <Link href="/console/notifications" className="bell__all" onClick={() => setOpen(false)}>
            See all notifications
          </Link>
        </div>
      ) : null}
    </div>
  );
}
