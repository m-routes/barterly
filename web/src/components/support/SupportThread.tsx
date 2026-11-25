"use client";

import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormError, TextArea } from "@/components/ui/fields";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { useLoad } from "@/lib/hooks/useLoad";
import { STATUS_TEXT } from "@/lib/support/kinds";

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

/** One request: the conversation with support, and a box to write back. */
export function SupportThread({ ticketId, backHref }: { ticketId: string; backHref: string }) {
  const { state, reload, setData } = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/support/tickets/{ticket_id}/", {
          params: { path: { ticket_id: ticketId } },
        }),
      ),
    `support-ticket-${ticketId}`,
  );
  const [body, setBody] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  if (state.status === "loading") return <LoadingState label="Loading your request…" />;
  if (state.status === "error") {
    return (
      <ErrorState
        title="We couldn't load this request"
        description={describeError(state.error)}
        retry={() => void reload()}
      />
    );
  }
  const ticket = state.data;

  async function send(event: React.FormEvent) {
    event.preventDefault();
    if (!body.trim()) {
      setError("Write a message.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const updated = await unwrap(
        api.POST("/api/v1/support/tickets/{ticket_id}/messages/", {
          params: { path: { ticket_id: ticketId } },
          body: { body: body.trim() },
        }),
      );
      setData(() => updated);
      setBody("");
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page page--narrow stack">
      <p>
        <Link href={backHref}>← Help and feedback</Link>
      </p>
      <header className="page__header">
        <h1 className="page__title">{ticket.subject}</h1>
        <p>
          {ticket.reference} · {STATUS_TEXT[ticket.status] ?? ticket.status}
          {ticket.reply_expected_by
            ? ` · We aim to answer by ${when(ticket.reply_expected_by)}`
            : ""}
        </p>
      </header>
      <ol className="support-thread" aria-label="Messages">
        {ticket.messages.map((message) => (
          <li
            key={message.id}
            className={`support-thread__message${message.from_staff ? " support-thread__message--staff" : ""}`}
          >
            <p className="support-thread__who">
              {message.from_staff ? "Barterly support" : "You"} · {when(message.created_at)}
            </p>
            <p className="support-thread__body">{message.body}</p>
          </li>
        ))}
      </ol>
      <form noValidate onSubmit={send} className="panel stack-sm">
        <TextArea
          label={ticket.status === "resolved" ? "Still need help? Write back" : "Reply"}
          rows={4}
          maxLength={5000}
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <FormError message={error} />
        <Button type="submit" busy={busy} busyLabel="Sending…">
          Send
        </Button>
      </form>
    </div>
  );
}
