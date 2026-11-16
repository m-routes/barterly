"use client";

import Link from "next/link";

import { ApplicationStatusChip, Chip } from "@/components/ui/StatusChip";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

/** Conversations with applicants, newest first. Loaded once: only an open chat polls. */
export function Inbox() {
  const { state, reload } = useLoad(
    () => unwrap(api.GET("/api/v1/conversations/", { params: { query: { page_size: 100 } } })),
    "inbox",
  );

  return (
    <div className="page">
      <header className="page__header">
        <h1 className="page__title">Messages</h1>
        <p className="page__lead">A chat opens when you shortlist or message an applicant.</p>
      </header>
      {state.status === "loading" ? <LoadingState label="Loading your messages…" /> : null}
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load your messages"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : null}
      {state.status === "ready" && state.data.results.length === 0 ? (
        <EmptyState
          title="No messages yet"
          description="Shortlist an applicant, or open one and choose Message, to start a chat."
          action={{ label: "Applicants", href: "/console/applicants" }}
        />
      ) : null}
      {state.status === "ready" && state.data.results.length ? (
        <ul className="inbox">
          {state.data.results.map((c) => (
            <li key={c.id}>
              <Link href={`/console/messages/${c.id}`} className="inbox__row">
                <span className="inbox__who">
                  <strong>{c.other.name}</strong>
                  <span className="field__hint">{c.gig_title}</span>
                </span>
                <span className="inbox__last">
                  {c.last_message
                    ? `${c.last_message.mine ? "You: " : ""}${c.last_message.body}`
                    : "No messages yet"}
                </span>
                <span className="inbox__meta">
                  <ApplicationStatusChip status={c.application_status} />
                  {c.unread ? <Chip tone="dark">{c.unread} unread</Chip> : null}
                  <span className="field__hint">
                    {formatDate(c.last_message_at ?? c.opened_at)}
                  </span>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
