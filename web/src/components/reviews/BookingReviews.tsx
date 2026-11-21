"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";
import { FormError, SelectField, TextArea } from "@/components/ui/fields";
import { api, unwrap } from "@/lib/api/client";
import { describeError } from "@/lib/api/errors";
import type { BookingReviews as Data, ReportReason, StayReview } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";

import { ReviewCard } from "./ReviewCard";

const CATEGORIES = ["communication", "accuracy", "safety", "reliability"] as const;
type Category = (typeof CATEGORIES)[number];

const REPORT_REASONS: Record<ReportReason, string> = {
  abusive: "Abusive or hateful",
  false: "Not true, or about something else",
  private: "Shares private information",
  spam: "Spam or advertising",
  other: "Something else",
};

/**
 * Reviews of a completed stay, double-blind: write yours; theirs appears once both are
 * in (or the 14-day window has closed). Reply once to the review of you; report one
 * that breaks the rules.
 */
export function BookingReviews({ bookingId }: { bookingId: string }) {
  const load = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/bookings/{booking_id}/reviews/", {
          params: { path: { booking_id: bookingId } },
        }),
      ),
    bookingId,
  );
  if (load.state.status !== "ready") return null;
  const data = load.state.data;
  return (
    <section className="panel stack-sm" aria-labelledby="reviews-title">
      <h2 id="reviews-title" className="panel__title">
        Reviews
      </h2>
      {data.can_review ? (
        <ReviewForm data={data} bookingId={bookingId} onDone={() => void load.reload()} />
      ) : null}
      {data.mine ? (
        <ReviewCard
          review={data.mine}
          heading="Your review"
          actions={
            data.mine.status === "published" ? null : (
              <p className="field__hint">
                {data.mine.status === "held"
                  ? "Barterly is checking it before it's published."
                  : "Hidden until they review too, or the window closes."}
              </p>
            )
          }
        />
      ) : null}
      {data.theirs ? (
        <ReviewCard
          review={data.theirs}
          heading="Their review of you"
          actions={<TheirReviewActions review={data.theirs} onDone={() => void load.reload()} />}
        />
      ) : data.they_have_reviewed ? (
        <p className="field__hint">
          They&apos;ve reviewed you. You&apos;ll see it once you review them, or when the window
          closes.
        </p>
      ) : null}
      {!data.can_review && !data.mine && data.window_closes_at ? (
        <p className="field__hint">The time to review this stay has passed.</p>
      ) : null}
    </section>
  );
}

function StarPicker({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <fieldset className="star-picker">
      <legend>{label}</legend>
      {[1, 2, 3, 4, 5].map((n) => (
        <label key={n}>
          <input
            type="radio"
            name={label}
            value={n}
            checked={value === n}
            onChange={() => onChange(n)}
          />
          <span aria-hidden="true">{n <= value ? "★" : "☆"}</span>
          <span className="visually-hidden">{n} out of 5</span>
        </label>
      ))}
    </fieldset>
  );
}

function ReviewForm({
  data,
  bookingId,
  onDone,
}: {
  data: Data;
  bookingId: string;
  onDone: () => void;
}) {
  const [rating, setRating] = useState(0);
  const [scores, setScores] = useState<Record<Category, number>>({
    communication: 0,
    accuracy: 0,
    safety: 0,
    reliability: 0,
  });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const complete = rating > 0 && CATEGORIES.every((c) => scores[c] > 0) && text.trim().length >= 20;
  return (
    <form
      className="stack-sm"
      onSubmit={async (e) => {
        e.preventDefault();
        setBusy(true);
        setError("");
        try {
          await unwrap(
            api.POST("/api/v1/bookings/{booking_id}/reviews/", {
              params: { path: { booking_id: bookingId } },
              body: { rating, ...scores, text: text.trim() },
            }),
          );
          onDone();
        } catch (err) {
          setError(describeError(err));
          setBusy(false);
        }
      }}
    >
      <p className="field__hint">
        Review the {data.reviewing === "talent" ? "talent" : "host"} by{" "}
        {formatDate(data.window_closes_at)}. Neither of you sees the other&apos;s review until both
        are in. Reviews can&apos;t be changed once published.
      </p>
      <StarPicker label="Overall" value={rating} onChange={setRating} />
      {CATEGORIES.map((c) => (
        <StarPicker
          key={c}
          label={data.category_labels[c] ?? c}
          value={scores[c]}
          onChange={(v) => setScores((s) => ({ ...s, [c]: v }))}
        />
      ))}
      <TextArea
        label="Your review"
        hint="At least 20 characters. No phone numbers, emails or links."
        value={text}
        maxLength={2000}
        onChange={(e) => setText(e.target.value)}
      />
      <FormError message={error} />
      <Button type="submit" busy={busy} disabled={!complete}>
        Submit review
      </Button>
    </form>
  );
}

function TheirReviewActions({ review, onDone }: { review: StayReview; onDone: () => void }) {
  const [replying, setReplying] = useState(false);
  const [reporting, setReporting] = useState(false);
  return (
    <div className="actions-row">
      {review.reply ? null : (
        <Button variant="secondary" className="button--small" onClick={() => setReplying(true)}>
          Reply
        </Button>
      )}
      <Button variant="ghost" className="button--small" onClick={() => setReporting(true)}>
        Report
      </Button>
      {replying ? (
        <ReplyDialog
          reviewId={review.id}
          onClose={() => setReplying(false)}
          onDone={() => {
            setReplying(false);
            onDone();
          }}
        />
      ) : null}
      {reporting ? <ReportDialog reviewId={review.id} onClose={() => setReporting(false)} /> : null}
    </div>
  );
}

function ReplyDialog({
  reviewId,
  onClose,
  onDone,
}: {
  reviewId: string;
  onClose: () => void;
  onDone: () => void;
}) {
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  return (
    <Dialog
      title="Reply to this review"
      description="You can reply once, and it can't be changed after."
      onClose={onClose}
      footer={
        <Button
          disabled={!text.trim()}
          onClick={async () => {
            try {
              await unwrap(
                api.POST("/api/v1/reviews/{review_id}/reply/", {
                  params: { path: { review_id: reviewId } },
                  body: { text: text.trim() },
                }),
              );
              onDone();
            } catch (e) {
              setError(describeError(e));
            }
          }}
        >
          Post reply
        </Button>
      }
    >
      <TextArea
        label="Your reply"
        value={text}
        maxLength={1000}
        onChange={(e) => setText(e.target.value)}
      />
      <FormError message={error} />
    </Dialog>
  );
}

function ReportDialog({ reviewId, onClose }: { reviewId: string; onClose: () => void }) {
  const [reason, setReason] = useState<ReportReason>("false");
  const [note, setNote] = useState("");
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");
  return (
    <Dialog
      title="Report this review"
      description="Barterly's team will look at it."
      onClose={onClose}
      footer={
        done ? (
          <Button onClick={onClose}>Close</Button>
        ) : (
          <Button
            onClick={async () => {
              try {
                await unwrap(
                  api.POST("/api/v1/reviews/{review_id}/report/", {
                    params: { path: { review_id: reviewId } },
                    body: { reason, note },
                  }),
                );
                setDone(true);
              } catch (e) {
                setError(describeError(e));
              }
            }}
          >
            Send report
          </Button>
        )
      }
    >
      {done ? (
        <p role="status">Thanks. We&apos;ll take a look.</p>
      ) : (
        <>
          <SelectField
            label="What's wrong"
            options={Object.entries(REPORT_REASONS).map(([value, label]) => ({ value, label }))}
            value={reason}
            onChange={(e) => setReason(e.target.value as ReportReason)}
          />
          <TextArea
            label="Anything to add"
            optional
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
          <FormError message={error} />
        </>
      )}
    </Dialog>
  );
}
