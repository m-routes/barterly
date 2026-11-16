"use client";

import Link from "next/link";
import { useId, useRef, useState } from "react";

import { ChatThread } from "@/components/chat/ChatThread";
import { Button } from "@/components/ui/Button";
import { Dialog, Tabs } from "@/components/ui/Dialog";
import { ApplicationStatusChip } from "@/components/ui/StatusChip";
import { FormError, TextArea, TextField } from "@/components/ui/fields";
import { ErrorState, LoadingState } from "@/components/ui/states";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, describeError } from "@/lib/api/errors";
import { notify } from "@/lib/api/events";
import type { components } from "@/lib/api/schema";
import { requestBody } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

import { ApplicantProfile } from "../ApplicantProfile";
import { OfferPanel } from "../OfferPanel";

type VendorApplication = components["schemas"]["VendorApplication"];
type Note = components["schemas"]["Note"];
type Interview = components["schemas"]["Interview"];

export type DrawerTab = "profile" | "notes" | "chat" | "interview" | "offer";
const TABS: ReadonlyArray<{ id: DrawerTab; label: string }> = [
  { id: "profile", label: "Profile" },
  { id: "notes", label: "Notes and tags" },
  { id: "chat", label: "Chat" },
  { id: "interview", label: "Interview" },
  { id: "offer", label: "Offer" },
];

/** One applicant, beside the board: profile and files, notes, chat, interview, offer. */
export function ApplicantDrawer({
  applicationId,
  tab,
  onTab,
  onClose,
  onChanged,
}: {
  applicationId: string;
  tab: DrawerTab;
  onTab: (tab: DrawerTab) => void;
  onClose: () => void;
  onChanged: () => void;
}) {
  const ids = useId();
  const { state, reload, refresh } = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/applications/{application_id}/", {
          params: { path: { application_id: applicationId } },
        }),
      ),
    applicationId,
  );
  const a = state.status === "ready" ? (state.data as VendorApplication) : null;

  function changed() {
    void refresh();
    onChanged();
  }

  return (
    <Dialog
      variant="drawer"
      title={a ? a.applicant.display_name : "Applicant"}
      description={
        a ? (
          <span className="drawer__sub">
            <ApplicationStatusChip status={a.status} />{" "}
            {[a.applicant.talent_type, a.applicant.home_city].filter(Boolean).join(" · ")} · applied{" "}
            {formatDate(a.applied_at)} · <Link href={`/console/applicants/${a.id}`}>Full page</Link>
          </span>
        ) : undefined
      }
      onClose={onClose}
    >
      {state.status === "loading" ? <LoadingState label="Loading the application…" /> : null}
      {state.status === "error" ? (
        <ErrorState
          title="We couldn't load this application"
          description={describeError(state.error)}
          retry={() => void reload()}
        />
      ) : null}
      {a ? (
        <>
          <Tabs
            label="Applicant sections"
            tabs={TABS}
            active={tab}
            onChange={onTab}
            idPrefix={ids}
          />
          <div
            role="tabpanel"
            id={`${ids}-panel-${tab}`}
            aria-labelledby={`${ids}-tab-${tab}`}
            className="drawer__panel stack"
            tabIndex={0}
          >
            {tab === "profile" ? <ApplicantProfile application={a} /> : null}
            {tab === "notes" ? <NotesAndTags application={a} onChanged={changed} /> : null}
            {tab === "chat" ? <ChatTab applicationId={a.id} /> : null}
            {tab === "interview" ? (
              <InterviewScheduler application={a} onChanged={changed} />
            ) : null}
            {tab === "offer" ? <OfferPanel application={a} onChange={changed} /> : null}
          </div>
        </>
      ) : null}
    </Dialog>
  );
}

// ---------- Notes and tags ----------

function NotesAndTags({
  application,
  onChanged,
}: {
  application: VendorApplication;
  onChanged: () => void;
}) {
  const path = { params: { path: { application_id: application.id } } };
  const [notes, setNotes] = useState<Note[]>(application.notes);
  const [tags, setTags] = useState<string[]>(application.tags);
  const [body, setBody] = useState("");
  const [tag, setTag] = useState("");
  const tempIds = useRef(0);

  async function addNote(event: React.FormEvent) {
    event.preventDefault();
    const text = body.trim();
    if (!text) return;
    const temp: Note = {
      id: `temp-${++tempIds.current}`,
      body: text,
      author: "You",
      created_at: "",
    };
    setNotes((n) => [temp, ...n]);
    setBody("");
    try {
      const saved = await unwrap(
        api.POST("/api/v1/applications/{application_id}/notes/", {
          ...path,
          body: requestBody<Note>({ body: text }),
        }),
      );
      setNotes((n) => n.map((x) => (x.id === temp.id ? saved : x)));
      onChanged();
    } catch (err) {
      setNotes((n) => n.filter((x) => x.id !== temp.id));
      setBody(text);
      notify(`Couldn't save the note: ${describeError(err)}`);
    }
  }

  async function removeNote(note: Note) {
    setNotes((n) => n.filter((x) => x.id !== note.id));
    try {
      await unwrap(
        api.DELETE("/api/v1/applications/{application_id}/notes/{note_id}/", {
          params: { path: { application_id: application.id, note_id: note.id } },
        }),
      );
      onChanged();
    } catch (err) {
      setNotes((n) => [note, ...n.filter((x) => x.id !== note.id)]);
      notify(`Couldn't delete the note: ${describeError(err)}`);
    }
  }

  async function saveTags(next: string[]) {
    const before = tags;
    setTags(next);
    try {
      const saved = await unwrap(
        api.PUT("/api/v1/applications/{application_id}/tags/", { ...path, body: { tags: next } }),
      );
      setTags(saved.tags);
      onChanged();
    } catch (err) {
      setTags(before);
      notify(`Couldn't update the tags: ${describeError(err)}`);
    }
  }

  return (
    <>
      <section className="panel stack-sm" aria-labelledby="tags-title">
        <h3 id="tags-title" className="panel__title">
          Tags
        </h3>
        <p className="field__hint">Only you see these. Filter the board by them.</p>
        {tags.length ? (
          <ul className="tag-list">
            {tags.map((t) => (
              <li key={t} className="tag">
                {t}
                <button
                  type="button"
                  className="tag__remove"
                  aria-label={`Remove tag ${t}`}
                  onClick={() => void saveTags(tags.filter((x) => x !== t))}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        ) : null}
        <form
          className="inline-form"
          onSubmit={(e) => {
            e.preventDefault();
            const t = tag.trim().toLowerCase();
            if (t && !tags.includes(t)) void saveTags([...tags, t]);
            setTag("");
          }}
        >
          <TextField
            label="Add a tag"
            maxLength={30}
            value={tag}
            disabled={tags.length >= 10}
            onChange={(e) => setTag(e.target.value)}
          />
          <Button type="submit" variant="secondary" disabled={!tag.trim() || tags.length >= 10}>
            Add
          </Button>
        </form>
      </section>

      <section className="panel stack-sm" aria-labelledby="notes-title">
        <h3 id="notes-title" className="panel__title">
          Private notes
        </h3>
        <form className="stack-sm" onSubmit={(e) => void addNote(e)}>
          <TextArea
            label="New note"
            maxLength={2000}
            rows={3}
            value={body}
            onChange={(e) => setBody(e.target.value)}
          />
          <div>
            <Button type="submit" variant="secondary" disabled={!body.trim()}>
              Add note
            </Button>
          </div>
        </form>
        {notes.length ? (
          <ul className="note-list">
            {notes.map((n) => (
              <li key={n.id} className="note-list__item">
                <p className="prewrap">{n.body}</p>
                <p className="field__hint">{n.created_at ? formatDate(n.created_at) : "Saving…"}</p>
                {n.id.startsWith("temp-") ? null : (
                  <Button variant="ghost" onClick={() => void removeNote(n)}>
                    Delete<span className="visually-hidden"> this note</span>
                  </Button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="field__hint">No notes yet.</p>
        )}
      </section>
    </>
  );
}

// ---------- Chat ----------

function ChatTab({ applicationId }: { applicationId: string }) {
  const { state, reload } = useLoad(
    () =>
      unwrap(
        api.POST("/api/v1/applications/{application_id}/conversation/", {
          params: { path: { application_id: applicationId } },
        }),
      ),
    `chat:${applicationId}`,
  );
  if (state.status === "loading") return <LoadingState label="Opening the chat…" />;
  if (state.status === "error") {
    return (
      <ErrorState
        title="We couldn't open the chat"
        description={describeError(state.error)}
        retry={() => void reload()}
      />
    );
  }
  return <ChatThread conversationId={state.data.id} backHref="/console/messages" embedded />;
}

// ---------- Interview ----------

const MAX_SLOTS = 3;

function InterviewScheduler({
  application,
  onChanged,
}: {
  application: VendorApplication;
  onChanged: () => void;
}) {
  const path = { params: { path: { application_id: application.id } } };
  const current = useLoad(async () => {
    try {
      return await unwrap(api.GET("/api/v1/applications/{application_id}/interview/", path));
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }
  }, `interview:${application.id}`);
  const [proposing, setProposing] = useState(false);

  if (current.state.status === "loading") return <LoadingState label="Loading the interview…" />;
  if (current.state.status === "error") {
    return (
      <ErrorState
        title="We couldn't load the interview"
        description={describeError(current.state.error)}
        retry={() => void current.reload()}
      />
    );
  }
  const interview = current.state.data;
  const open = interview && interview.status !== "cancelled";

  async function cancel() {
    try {
      await unwrap(
        api.POST("/api/v1/applications/{application_id}/interview/cancel/", { ...path, body: {} }),
      );
      void current.reload();
      onChanged();
    } catch (err) {
      notify(`Couldn't cancel the interview: ${describeError(err)}`);
    }
  }

  return (
    <section className="panel stack-sm" aria-labelledby="interview-title">
      <h3 id="interview-title" className="panel__title">
        Interview
      </h3>
      {open ? <InterviewSummary interview={interview} /> : null}
      {open && !proposing ? (
        <div className="actions-row actions-row--start">
          {interview.status === "new_times_requested" ? (
            <Button onClick={() => setProposing(true)}>Offer new times</Button>
          ) : null}
          <Button variant="ghost" onClick={() => void cancel()}>
            Cancel interview
          </Button>
        </div>
      ) : null}
      {!open && !proposing ? (
        <div className="stack-sm">
          <p>
            Offer up to {MAX_SLOTS} times for a video call. {application.applicant.display_name}{" "}
            picks one, and you both get reminders.
          </p>
          <div>
            <Button onClick={() => setProposing(true)}>Propose times</Button>
          </div>
        </div>
      ) : null}
      {proposing ? (
        <ProposeForm
          applicationId={application.id}
          onDone={(saved) => {
            setProposing(false);
            if (saved) {
              current.setData(() => saved);
              onChanged();
            }
          }}
        />
      ) : null}
    </section>
  );
}

const INTERVIEW_LABELS: Record<Interview["status"], string> = {
  proposed: "Waiting for them to pick a time",
  scheduled: "Scheduled",
  new_times_requested: "They asked for other times",
  cancelled: "Cancelled",
};

function InterviewSummary({ interview }: { interview: Interview }) {
  return (
    <dl className="summary">
      <div>
        <dt>Status</dt>
        <dd>{INTERVIEW_LABELS[interview.status]}</dd>
      </div>
      {interview.starts_at_ist ? (
        <div>
          <dt>When</dt>
          <dd>
            {interview.starts_at_ist} ({interview.duration_minutes} minutes)
          </dd>
        </div>
      ) : (
        <div>
          <dt>Times offered</dt>
          <dd>
            <ul className="plain-list">
              {interview.slots.map((s) => (
                <li key={s.id}>{s.starts_at_ist}</li>
              ))}
            </ul>
          </dd>
        </div>
      )}
      {interview.video_link ? (
        <div>
          <dt>Video link</dt>
          <dd>
            <a href={interview.video_link} target="_blank" rel="noopener noreferrer">
              {interview.video_link}
            </a>
          </dd>
        </div>
      ) : null}
    </dl>
  );
}

function ProposeForm({
  applicationId,
  onDone,
}: {
  applicationId: string;
  onDone: (saved: Interview | null) => void;
}) {
  const [slots, setSlots] = useState<string[]>([""]);
  const [link, setLink] = useState("");
  const [minutes, setMinutes] = useState(30);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const filled = slots.filter(Boolean);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const saved = await unwrap(
        api.POST("/api/v1/applications/{application_id}/interview/", {
          params: { path: { application_id: applicationId } },
          // datetime-local has no offset: the API reads it as India time.
          body: { slots: filled, video_link: link.trim(), duration_minutes: minutes, note },
        }),
      );
      onDone(saved);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="stack-sm" onSubmit={(e) => void submit(e)} noValidate>
      <fieldset className="stack-sm">
        <legend className="field__label">Times you can do (India time)</legend>
        {slots.map((value, index) => (
          <div key={index} className="inline-form">
            <TextField
              label={`Time ${index + 1}`}
              type="datetime-local"
              value={value}
              onChange={(e) => setSlots((s) => s.map((x, i) => (i === index ? e.target.value : x)))}
            />
            {slots.length > 1 ? (
              <Button
                variant="ghost"
                onClick={() => setSlots((s) => s.filter((_, i) => i !== index))}
              >
                Remove<span className="visually-hidden"> time {index + 1}</span>
              </Button>
            ) : null}
          </div>
        ))}
        {slots.length < MAX_SLOTS ? (
          <div>
            <Button variant="ghost" onClick={() => setSlots((s) => [...s, ""])}>
              Add another time
            </Button>
          </div>
        ) : null}
      </fieldset>
      <TextField
        label="Video call link"
        type="url"
        placeholder="https://meet.google.com/…"
        value={link}
        onChange={(e) => setLink(e.target.value)}
      />
      <TextField
        label="Length (minutes)"
        type="number"
        min={10}
        max={180}
        value={minutes}
        onChange={(e) => setMinutes(Number(e.target.value))}
      />
      <TextArea
        label="Note for them"
        optional
        maxLength={500}
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <FormError message={error} />
      <div className="actions-row actions-row--start">
        <Button type="submit" busy={busy} disabled={!filled.length || !link.trim()}>
          Send times
        </Button>
        <Button variant="ghost" disabled={busy} onClick={() => onDone(null)}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
