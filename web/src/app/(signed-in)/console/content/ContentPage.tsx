"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { Chip, type ChipTone } from "@/components/ui/StatusChip";
import { FormError, TextArea } from "@/components/ui/fields";
import { EmptyState, ErrorState, LoadingState } from "@/components/ui/states";
import { USAGE_SCOPE_LABELS } from "@/lib/agreements/terms";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { LibraryItem, PostStats, TrackedDeliverable } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

type Tab = "review" | "library";

/**
 * Talent's work for barter and hybrid gigs: what's waiting for review (with the
 * collaboration-label check and post stats), and the library of approved content with
 * its usage rights and downloads.
 */
export function ContentPage() {
  const [tab, setTab] = useState<Tab>("review");
  return (
    <div className="page stack">
      <header className="page__header">
        <h1 className="page__title">Content</h1>
        <p className="field__hint">
          What talent hand in for barter and hybrid gigs. Approving everything releases a hybrid
          gig&apos;s stipend; with no answer for 72 hours after the last one, it&apos;s approved
          automatically.
        </p>
      </header>
      <div className="filter-chips" role="tablist" aria-label="Content">
        {(
          [
            ["review", "To review"],
            ["library", "Library"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={`filter-chip${tab === key ? " filter-chip--on" : ""}`}
            onClick={() => setTab(key)}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "review" ? <ToReview /> : <Library />}
    </div>
  );
}

function ToReview() {
  const load = useLoad(() => unwrap(api.GET("/api/v1/content/to-review/")), "to-review");
  const [reviewing, setReviewing] = useState<TrackedDeliverable | null>(null);
  const [error, setError] = useState("");

  if (load.state.status === "loading") return <LoadingState label="Loading submissions…" />;
  if (load.state.status === "error") {
    return (
      <ErrorState
        title="We couldn't load submissions"
        description="Check your connection and try again."
        retry={() => void load.reload()}
      />
    );
  }
  const rows = load.state.data.results;
  if (!rows.length) {
    return (
      <EmptyState
        title="Nothing to review"
        description="When talent hand in their work, it shows up here."
      />
    );
  }

  async function approve(d: TrackedDeliverable) {
    setError("");
    try {
      await unwrap(
        api.POST("/api/v1/deliverables/items/{deliverable_id}/review/", {
          params: { path: { deliverable_id: d.id } },
          body: { approve: true, note: "" },
        }),
      );
      await load.reload();
    } catch (e) {
      setError(describeError(e));
    }
  }

  return (
    <section className="stack-sm" aria-label="Waiting for review">
      <FormError message={error} />
      <ul className="card-list">
        {rows.map((d) => (
          <li key={d.id} className="card-list__item content-card">
            <div className="card-list__main stack-sm">
              <div>
                <p className="card-list__title">{d.title}</p>
                <p className="card-list__meta">
                  {d.gig_title} · due {formatDate(d.due_date)}
                </p>
              </div>
              <SubmissionView deliverable={d} />
              <StatsView stats={d.stats} />
            </div>
            <div className="actions-row">
              <Button className="button--small" onClick={() => void approve(d)}>
                Approve
              </Button>
              <Button variant="secondary" className="button--small" onClick={() => setReviewing(d)}>
                Ask for changes
              </Button>
            </div>
          </li>
        ))}
      </ul>
      {reviewing ? (
        <ChangesDialog
          deliverable={reviewing}
          onClose={() => setReviewing(null)}
          onDone={async () => {
            setReviewing(null);
            await load.reload();
          }}
        />
      ) : null}
    </section>
  );
}

const DETECTED: Record<"true" | "false" | "null", { label: string; tone: ChipTone }> = {
  true: { label: "Label found in the caption", tone: "success" },
  false: { label: "Label not found in the caption", tone: "danger" },
  null: { label: "Caption not checked", tone: "pending" },
};

export function SubmissionView({ deliverable }: { deliverable: TrackedDeliverable }) {
  const s = deliverable.latest_submission;
  if (!s) return <p className="field__hint">Not handed in yet.</p>;
  const detected = DETECTED[String(s.disclosure_detected) as keyof typeof DETECTED];
  return (
    <div className="stack-sm">
      {s.post_url ? (
        <a href={s.post_url} target="_blank" rel="noopener noreferrer">
          Open the post
        </a>
      ) : null}
      {s.files.length ? (
        <ul className="chip-row" aria-label="Files">
          {s.files.map((f, i) => (
            <li key={f.id}>
              <a href={f.url} target="_blank" rel="noopener noreferrer">
                {f.content_type.startsWith("video/") ? "Video" : "Photo"} {i + 1}
              </a>
            </li>
          ))}
        </ul>
      ) : null}
      {s.note ? <p className="field__hint">“{s.note}”</p> : null}
      {deliverable.disclosure_required ? (
        <div className="chip-row" aria-label="Collaboration label">
          <Chip tone={s.disclosure_confirmed ? "success" : "danger"}>
            {s.disclosure_confirmed
              ? "Talent confirms the #collab / #ad label"
              : "Label not confirmed"}
          </Chip>
          <Chip tone={detected.tone}>{detected.label}</Chip>
        </div>
      ) : null}
      <p className="field__hint">
        Version {s.version} · {deliverable.change_rounds_left} round(s) of changes left
      </p>
    </div>
  );
}

function number(value: number | null): string {
  return value === null ? "–" : value.toLocaleString("en-IN");
}

export function StatsView({ stats }: { stats: PostStats[] }) {
  if (!stats.length) return null;
  return (
    <ul className="stack-sm" aria-label="Post stats">
      {stats.map((s) => (
        <li key={`${s.source}-${s.captured_at}`} className="chip-row">
          <Chip tone={s.self_reported ? "warning" : "neutral"}>
            {s.self_reported
              ? "Self-reported"
              : `From ${s.source === "youtube" ? "YouTube" : "Instagram"}`}
          </Chip>
          <span>
            {number(s.views)} views · {number(s.likes)} likes · {number(s.comments)} comments
          </span>
          <span className="field__hint">{formatDate(s.captured_at)}</span>
          {s.screenshot_url ? (
            <a href={s.screenshot_url} target="_blank" rel="noopener noreferrer">
              Screenshot
            </a>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function ChangesDialog({
  deliverable,
  onClose,
  onDone,
}: {
  deliverable: TrackedDeliverable;
  onClose: () => void;
  onDone: () => Promise<void>;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const noneLeft = deliverable.change_rounds_left <= 0;
  return (
    <Dialog
      title={`Ask for changes to ${deliverable.title}?`}
      description={
        noneLeft
          ? "You've used both rounds of changes. Approve it, or open a dispute on the booking."
          : `You can ask ${deliverable.change_rounds_left} more time(s).`
      }
      onClose={onClose}
      footer={
        <Button
          busy={busy}
          disabled={noneLeft || !note.trim()}
          onClick={async () => {
            setBusy(true);
            try {
              await unwrap(
                api.POST("/api/v1/deliverables/items/{deliverable_id}/review/", {
                  params: { path: { deliverable_id: deliverable.id } },
                  body: { approve: false, note: note.trim() },
                }),
              );
              await onDone();
            } catch (e) {
              setError(describeError(e));
              setBusy(false);
            }
          }}
        >
          Ask for changes
        </Button>
      }
    >
      {noneLeft ? null : (
        <TextArea
          label="What needs to change"
          value={note}
          maxLength={1000}
          onChange={(e) => setNote(e.target.value)}
        />
      )}
      <FormError message={error} />
    </Dialog>
  );
}

function Library() {
  const load = useLoad(() => unwrap(api.GET("/api/v1/content/library/")), "library");
  if (load.state.status === "loading") return <LoadingState label="Loading your library…" />;
  if (load.state.status === "error") {
    return (
      <ErrorState
        title="We couldn't load your library"
        description="Check your connection and try again."
        retry={() => void load.reload()}
      />
    );
  }
  const rows = load.state.data.results;
  if (!rows.length) {
    return (
      <EmptyState
        title="No approved content yet"
        description="Content you approve appears here, with how you may use it."
      />
    );
  }
  return (
    <ul className="card-list" aria-label="Approved content">
      {rows.map((item) => (
        <LibraryCard key={item.id} item={item} />
      ))}
    </ul>
  );
}

function LibraryCard({ item }: { item: LibraryItem }) {
  const rights = item.usage_rights;
  return (
    <li className="card-list__item content-card">
      <div className="card-list__main stack-sm">
        <div>
          <p className="card-list__title">{item.title}</p>
          <p className="card-list__meta">
            {item.talent_name} · {item.gig_title} · approved {formatDate(item.approved_at)}
          </p>
        </div>
        {rights ? (
          <div className="usage-rights" aria-label="Usage rights">
            <p>
              <strong>You may use it on:</strong> {USAGE_SCOPE_LABELS[rights.scope]}
            </p>
            <p>
              <strong>Until:</strong> {formatDate(item.usable_until)} ({rights.duration_months}{" "}
              months from approval)
            </p>
            <p>
              <strong>Credit:</strong>{" "}
              {rights.credit_required ? "Credit the talent when you use it" : "Not required"}
            </p>
          </div>
        ) : null}
        {item.latest_submission?.post_url ? (
          <a href={item.latest_submission.post_url} target="_blank" rel="noopener noreferrer">
            Open the post
          </a>
        ) : null}
        <StatsView stats={item.stats} />
      </div>
      {item.downloads.length ? (
        <div className="actions-row">
          {item.downloads.map((d, i) => (
            <a key={d.id} className="button button--secondary button--small" href={d.url}>
              Download {d.content_type.startsWith("video/") ? "video" : "photo"} {i + 1}
            </a>
          ))}
        </div>
      ) : null}
    </li>
  );
}
