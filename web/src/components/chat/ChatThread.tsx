"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ApplicationStatusChip } from "@/components/ui/StatusChip";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import { CHAT_ACCEPT, attachmentProblem, chatMediaKind } from "@/lib/chat/attachments";
import { PollingTransport } from "@/lib/chat/polling";
import {
  type ChatMessage,
  type ChatTransport,
  type ConversationDetail,
  type ReportReason,
  cursorAfter,
  newClientId,
} from "@/lib/chat/transport";
import { useLoad } from "@/lib/hooks/useLoad";
import { uploadFile } from "@/lib/media/upload";

let shared: ChatTransport | undefined;
function defaultTransport(): ChatTransport {
  shared ??= new PollingTransport();
  return shared;
}

export const REPORT_REASONS: { value: ReportReason; label: string }[] = [
  { value: "spam", label: "Spam" },
  { value: "harassment", label: "Harassment or abuse" },
  { value: "scam", label: "Scam or fraud" },
  { value: "contact_sharing", label: "Asking to move off Barterly" },
  { value: "inappropriate", label: "Inappropriate content" },
  { value: "other", label: "Something else" },
];

function merge(current: ChatMessage[], incoming: ChatMessage[]): ChatMessage[] {
  const byId = new Map(current.map((m) => [m.id, m]));
  for (const m of incoming) byId.set(m.id, m);
  return [...byId.values()].sort((a, b) => Number(a.cursor) - Number(b.cursor));
}

function time(iso: string): string {
  return new Date(iso).toLocaleString("en-IN", {
    day: "numeric",
    month: "short",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
  });
}

function ReportForm({ messageId, onDone }: { messageId: string; onDone: (note: string) => void }) {
  const [reason, setReason] = useState<ReportReason>("spam");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async () => {
    setBusy(true);
    setError("");
    try {
      await unwrap(
        api.POST("/api/v1/messages/{message_id}/report/", {
          params: { path: { message_id: messageId } },
          body: { reason },
        }),
      );
      onDone("Thanks. Our team will review this message.");
    } catch (e) {
      setError(describeError(e));
      setBusy(false);
    }
  };
  return (
    <div className="chat-report">
      <label>
        <span className="visually-hidden">Why are you reporting this?</span>
        <select
          aria-label="Why are you reporting this?"
          value={reason}
          onChange={(e) => setReason(e.target.value as ReportReason)}
        >
          {REPORT_REASONS.map((r) => (
            <option key={r.value} value={r.value}>
              {r.label}
            </option>
          ))}
        </select>
      </label>
      <Button variant="secondary" busy={busy} onClick={() => void submit()}>
        Send report
      </Button>
      {error ? <p className="field__error">{error}</p> : null}
    </div>
  );
}

function Bubble({
  message,
  seen,
  canReport,
}: {
  message: ChatMessage;
  seen: boolean;
  canReport: boolean;
}) {
  const [reporting, setReporting] = useState(false);
  const [reported, setReported] = useState("");
  return (
    <li className={`chat-msg ${message.mine ? "chat-msg--mine" : ""}`}>
      <div className="chat-msg__bubble">
        {message.body ? <p className="prewrap">{message.body}</p> : null}
        {message.attachments.length ? (
          <ul className="chat-msg__files">
            {message.attachments.map((a) => (
              <li key={a.id}>
                {a.url ? (
                  <a href={a.url} target="_blank" rel="noopener noreferrer">
                    {a.kind === "image" ? "Photo" : "PDF"}
                  </a>
                ) : (
                  <span className="field__hint">File still processing</span>
                )}
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <div className="chat-msg__meta">
        <time dateTime={message.created_at}>{time(message.created_at)}</time>
        {message.masked ? <span> · contact details hidden</span> : null}
        {message.mine && seen ? <span> · Seen</span> : null}
        {canReport && !reported && !reporting ? (
          <button type="button" className="link-button" onClick={() => setReporting(true)}>
            Report
          </button>
        ) : null}
      </div>
      {reporting && !reported ? (
        <ReportForm
          messageId={message.id}
          onDone={(note) => {
            setReported(note);
            setReporting(false);
          }}
        />
      ) : null}
      {reported ? <p className="field__hint">{reported}</p> : null}
    </li>
  );
}

/**
 * One conversation: history, live updates through the transport (polling today),
 * a composer, read receipts, reporting and blocking.
 */
export function ChatThread({
  conversationId,
  transport = defaultTransport(),
  backHref,
  embedded = false,
}: {
  conversationId: string;
  transport?: ChatTransport;
  backHref: string;
  /** Inside another screen (the applicant drawer): no page frame or back link. */
  embedded?: boolean;
}) {
  const detail = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/conversations/{conversation_id}/", {
          params: { path: { conversation_id: conversationId } },
        }),
      ),
    conversationId,
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [hasEarlier, setHasEarlier] = useState(false);
  const [readUpTo, setReadUpTo] = useState("0");
  const [historyError, setHistoryError] = useState<unknown>(null);
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState("");
  const [sendError, setSendError] = useState("");
  const lastRead = useRef("0");
  const fileInput = useRef<HTMLInputElement>(null);

  // First page, then subscribe for anything newer.
  useEffect(() => {
    let live = true;
    let stop: (() => void) | undefined;
    transport
      .history(conversationId)
      .then((page) => {
        if (!live) return;
        setMessages(page.messages);
        setHasEarlier(page.hasEarlier);
        setReadUpTo(page.otherReadUpTo);
        setCursor(page.cursor);
        stop = transport.subscribe(conversationId, page.cursor, {
          onMessages: (batch) => {
            setMessages((m) => merge(m, batch.messages));
            setReadUpTo(batch.otherReadUpTo);
            setCursor(batch.cursor);
          },
        });
      })
      .catch((e: unknown) => live && setHistoryError(e));
    return () => {
      live = false;
      stop?.();
    };
  }, [conversationId, transport]);

  // Tell the server what I've seen from the other side.
  useEffect(() => {
    const newestTheirs = [...messages].reverse().find((m) => !m.mine);
    if (newestTheirs && cursorAfter(newestTheirs.cursor, lastRead.current)) {
      lastRead.current = newestTheirs.cursor;
      void transport.markRead(conversationId, newestTheirs.cursor).catch(() => undefined);
    }
  }, [messages, conversationId, transport]);

  const loadEarlier = useCallback(async () => {
    const first = messages[0];
    if (!first) return;
    const page = await transport.history(conversationId, first.cursor);
    setMessages((m) => merge(m, page.messages));
    setHasEarlier(page.hasEarlier);
  }, [messages, transport, conversationId]);

  const send = async () => {
    const text = body.trim();
    if (!text && !files.length) return;
    setSending(true);
    setSendError("");
    setNotice("");
    try {
      const attachmentIds: string[] = [];
      for (const file of files) {
        attachmentIds.push((await uploadFile(file, chatMediaKind(file))).mediaId);
      }
      const result = await transport.send(conversationId, {
        body: text,
        attachmentIds,
        clientId: newClientId(),
      });
      setMessages((m) => merge(m, [result.message]));
      setNotice(result.notice);
      setBody("");
      setFiles([]);
    } catch (e) {
      setSendError(describeError(e));
    } finally {
      setSending(false);
    }
  };

  const toggleBlock = async (conversation: ConversationDetail) => {
    if (!conversation.blocked_by_me && !window.confirm(`Block ${conversation.other.name}?`)) return;
    const path = { params: { path: { conversation_id: conversationId } } };
    const updated = await unwrap(
      conversation.blocked_by_me
        ? api.DELETE("/api/v1/conversations/{conversation_id}/block/", path)
        : api.POST("/api/v1/conversations/{conversation_id}/block/", path),
    );
    detail.setData(() => updated);
  };

  if (detail.state.status === "loading") return <LoadingState label="Loading the chat…" />;
  if (detail.state.status === "error" || historyError) {
    return (
      <div className="page">
        <ErrorState
          title="We couldn't load this chat"
          description={describeError(
            detail.state.status === "error" ? detail.state.error : historyError,
          )}
          retry={() => void detail.reload()}
          action={{ label: "All messages", href: backHref }}
        />
      </div>
    );
  }
  const c = detail.state.data;

  return (
    <div className={embedded ? "chat chat--embedded" : "page page--narrow chat"}>
      <header className={embedded ? "chat__header" : "page__header"}>
        {embedded ? null : (
          <Link href={backHref} className="back-link">
            All messages
          </Link>
        )}
        <div className="page__title-row">
          {embedded ? (
            <h3 className="panel__title">Chat with {c.other.name}</h3>
          ) : (
            <h1 className="page__title">{c.other.name}</h1>
          )}
          <ApplicationStatusChip status={c.application_status} />
        </div>
        {embedded ? null : (
          <p className="page__lead">
            About {c.gig_title} ·{" "}
            <Link href={`/console/applicants/${c.application}`}>View application</Link>
          </p>
        )}
        <div className="chat__actions">
          <Button variant="ghost" onClick={() => void toggleBlock(c)}>
            {c.blocked_by_me ? "Unblock" : "Block"}
          </Button>
        </div>
      </header>

      {!c.contact_sharing_allowed ? (
        <p className="note">
          Phone numbers, emails and links are hidden until the booking is confirmed. Keep the
          conversation on Barterly so you&apos;re both covered.
        </p>
      ) : null}

      <section className="panel chat__log" aria-label="Messages" aria-live="polite">
        {hasEarlier ? (
          <Button variant="ghost" onClick={() => void loadEarlier()}>
            Load earlier messages
          </Button>
        ) : null}
        {cursor === null ? <LoadingState label="Loading messages…" /> : null}
        {cursor !== null && !messages.length ? (
          <p className="field__hint">No messages yet. Say hello.</p>
        ) : null}
        <ol className="chat__messages">
          {messages.map((m) => (
            <Bubble
              key={m.id}
              message={m}
              seen={!cursorAfter(m.cursor, readUpTo)}
              canReport={!m.mine}
            />
          ))}
        </ol>
      </section>

      {c.can_send ? (
        <form
          className="chat__composer"
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
        >
          <label className="visually-hidden" htmlFor="chat-body">
            Message
          </label>
          <textarea
            id="chat-body"
            rows={2}
            maxLength={2000}
            value={body}
            placeholder={`Message ${c.other.name}`}
            onChange={(e) => setBody(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
          />
          <input
            ref={fileInput}
            type="file"
            accept={CHAT_ACCEPT}
            multiple
            hidden
            aria-label="Attach photos or PDFs"
            onChange={(e) => {
              const picked = [...(e.target.files ?? [])];
              const problem = attachmentProblem(picked, files.length);
              setSendError(problem ?? "");
              if (!problem) setFiles((f) => [...f, ...picked]);
              e.target.value = "";
            }}
          />
          <div className="chat__composer-row">
            <Button variant="secondary" onClick={() => fileInput.current?.click()}>
              Attach
            </Button>
            {files.length ? (
              <span className="field__hint">
                {files.map((f) => f.name).join(", ")}{" "}
                <button type="button" className="link-button" onClick={() => setFiles([])}>
                  Remove
                </button>
              </span>
            ) : null}
            <Button type="submit" busy={sending} busyLabel="Sending…">
              Send
            </Button>
          </div>
          {notice ? (
            <p className="note note--warning" role="status">
              {notice}
            </p>
          ) : null}
          {sendError ? (
            <p className="field__error" role="alert">
              {sendError}
            </p>
          ) : null}
        </form>
      ) : (
        <p className="note" role="status">
          {c.cant_send_reason}
        </p>
      )}
    </div>
  );
}
