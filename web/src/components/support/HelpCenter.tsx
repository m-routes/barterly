"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { FormError, SelectField, TextArea, TextField } from "@/components/ui/fields";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { track } from "@/lib/analytics/track";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { SupportKind, SupportTicket } from "@/lib/api/types";
import { useLoad } from "@/lib/hooks/useLoad";
import { STATUS_TEXT, SUPPORT_KINDS } from "@/lib/support/kinds";

function when(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

/** Help and feedback: write to the support team, and see earlier requests. */
export function HelpCenter({ basePath, screen }: { basePath: string; screen?: string }) {
  const { state, reload } = useLoad(async () => {
    const data = await unwrap(api.GET("/api/v1/support/tickets/"));
    return Array.isArray(data) ? data : (data as { results: SupportTicket[] }).results;
  }, "support-tickets");

  return (
    <div className="page page--narrow stack">
      <header className="page__header">
        <h1 className="page__title">Help and feedback</h1>
        <p>
          Write to the Barterly team. We reply here and send you a notification. In an emergency,
          call 112.
        </p>
      </header>
      <NewRequest basePath={basePath} screen={screen} onSent={() => void reload()} />
      <section className="panel stack-sm" aria-labelledby="requests-title">
        <h2 id="requests-title" className="panel__title">
          Your requests
        </h2>
        {state.status === "loading" ? (
          <LoadingState label="Loading your requests…" />
        ) : state.status === "error" ? (
          <ErrorState
            title="We couldn't load your requests"
            description={describeError(state.error)}
            retry={() => void reload()}
          />
        ) : state.data.length === 0 ? (
          <EmptyState title="Nothing yet" description="Requests you send appear here." />
        ) : (
          <ul className="support-list">
            {state.data.map((ticket) => (
              <li key={ticket.id} className="support-list__item">
                <Link href={`${basePath}/${ticket.id}`}>{ticket.subject}</Link>
                <span className="support-list__meta">
                  {ticket.reference} · {STATUS_TEXT[ticket.status] ?? ticket.status} ·{" "}
                  {when(ticket.last_message_at)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function NewRequest({
  basePath,
  screen,
  onSent,
}: {
  basePath: string;
  screen?: string;
  onSent: () => void;
}) {
  const router = useRouter();
  const [kind, setKind] = useState<SupportKind | "">("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const hint = SUPPORT_KINDS.find((k) => k.value === kind)?.hint;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const problems: Record<string, string> = {};
    if (!kind) problems.kind = "Choose what it's about.";
    if (!subject.trim()) problems.subject = "Give it a short title.";
    if (!body.trim()) problems.body = "Tell us what happened.";
    setErrors(problems);
    if (Object.keys(problems).length || !kind) return;
    setBusy(true);
    try {
      const ticket = await unwrap(
        api.POST("/api/v1/support/tickets/", {
          body: {
            kind,
            subject: subject.trim(),
            body: body.trim(),
            platform: "web",
            ...(screen ? { screen } : {}),
          },
        }),
      );
      track("feedback_sent", { kind });
      onSent();
      router.push(`${basePath}/${ticket.id}`);
    } catch (error) {
      setErrors({ root: describeError(error) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form noValidate onSubmit={submit} className="panel stack-sm" aria-labelledby="new-title">
      <h2 id="new-title" className="panel__title">
        Write to us
      </h2>
      <SelectField
        label="What's it about?"
        options={SUPPORT_KINDS}
        value={kind}
        onChange={(e) => setKind(e.target.value as SupportKind)}
        error={errors.kind}
        hint={hint}
      />
      <TextField
        label="Title"
        maxLength={120}
        value={subject}
        onChange={(e) => setSubject(e.target.value)}
        error={errors.subject}
      />
      <TextArea
        label="Message"
        maxLength={5000}
        rows={6}
        value={body}
        onChange={(e) => setBody(e.target.value)}
        error={errors.body}
        hint="Don't include card or bank details."
      />
      <FormError message={errors.root} />
      <Button type="submit" busy={busy} busyLabel="Sending…">
        Send
      </Button>
    </form>
  );
}
