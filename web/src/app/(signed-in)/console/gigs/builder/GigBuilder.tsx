"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import { GigPreviewCard } from "@/components/gigs/GigPreviewCard";
import { Button } from "@/components/ui/Button";
import { GigStatusChip } from "@/components/ui/StatusChip";
import { api, unwrap } from "@/lib/api/client";
import { formatDate } from "@/lib/format";
import { ApiError, describeError, fieldErrors } from "@/lib/api/errors";
import type { Gig, GigStatus, Property, Skill } from "@/lib/api/types";
import {
  REVIEWED_FIELDS,
  canCreate,
  draftFromGig,
  emptyDraft,
  toPayload,
  type GigDraft,
} from "@/lib/gigs/draft";
import { useGigSaver, type SaveState } from "@/lib/gigs/useGigSaver";
import {
  STEPS,
  checkComplete,
  checkShape,
  stepOf,
  type GigErrors,
  type GigField,
  type StepId,
} from "@/lib/validation/gig";

import { BasicsStep, PayStep, QuestionsStep, WhoStep } from "./GigSteps";

const AUTOSAVE_DELAY_MS = 1200;
const EDITABLE: ReadonlySet<GigStatus> = new Set(["draft", "in_review", "live", "paused"]);

function SaveStatus({ state, autosave }: { state: SaveState; autosave: boolean }) {
  let text = "";
  switch (state.kind) {
    case "waiting":
      text = "Your draft saves once it has a role, title, property and pay model.";
      break;
    case "invalid":
      text = "Fix the highlighted fields to save.";
      break;
    case "saving":
      text = "Saving…";
      break;
    case "saved":
      text = `${autosave ? "Draft saved" : "Saved"} at ${state.at.toLocaleTimeString("en-IN", {
        hour: "numeric",
        minute: "2-digit",
      })}`;
      break;
    case "error":
      text = `Not saved. ${state.message}`;
      break;
    default:
      text = autosave ? "Changes save automatically." : "";
  }
  return (
    <p
      className={`save-status${state.kind === "error" ? " save-status--error" : ""}`}
      role="status"
      aria-live="polite"
    >
      {text}
    </p>
  );
}

function ReviewStep({
  draft,
  problems,
  goTo,
  property,
}: {
  draft: GigDraft;
  problems: GigErrors;
  goTo: (step: StepId) => void;
  property?: Property;
}) {
  const byStep = STEPS.filter((s) => s.id !== "review").map((step) => ({
    step,
    messages: step.fields.flatMap((f) =>
      problems[f] ? [{ field: f, message: problems[f]! }] : [],
    ),
  }));
  const total = byStep.reduce((n, s) => n + s.messages.length, 0);
  const payload = toPayload(draft);
  return (
    <div className="stack">
      {total ? (
        <section className="review-problems" aria-labelledby="review-problems-title">
          <h3 id="review-problems-title" className="review-problems__title">
            {total} thing{total === 1 ? "" : "s"} to fix before review
          </h3>
          {byStep
            .filter((s) => s.messages.length)
            .map(({ step, messages }) => (
              <div key={step.id} className="review-problems__group">
                <div className="review-problems__header">
                  <h4>{step.label}</h4>
                  <Button variant="ghost" onClick={() => goTo(step.id)}>
                    Fix in {step.label}
                  </Button>
                </div>
                <ul>
                  {messages.map((m) => (
                    <li key={m.field}>
                      <span className="review-problems__field">{FIELD_LABELS[m.field]}:</span>{" "}
                      {m.message}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
        </section>
      ) : (
        <p className="note note--success">
          Everything&apos;s filled in. Our team checks every gig before it goes live, usually within
          a day.
        </p>
      )}
      <dl className="summary">
        <div>
          <dt>Property</dt>
          <dd>{property ? `${property.name}, ${property.city}` : "Not chosen"}</dd>
        </div>
        <div>
          <dt>Dates</dt>
          <dd>
            {payload.start_date ? formatDate(payload.start_date) : "No start date"}
            {payload.end_date ? ` to ${formatDate(payload.end_date)}` : ""}
            {payload.duration_days ? ` for ${payload.duration_days} days` : ""}
            {payload.apply_by ? ` · apply by ${formatDate(payload.apply_by)}` : ""}
          </dd>
        </div>
        <div>
          <dt>Questions</dt>
          <dd>{payload.screening_questions.length || "None"}</dd>
        </div>
      </dl>
    </div>
  );
}

const FIELD_LABELS: Record<GigField, string> = {
  property: "Property",
  title: "Title",
  description: "Description",
  role_template: "Role",
  compensation_model: "Pay model",
  slots: "Slots",
  start_date: "Start date",
  end_date: "End date",
  duration_days: "Length",
  apply_by: "Apply by",
  hours_per_day: "Hours per day",
  days_per_week: "Days per week",
  stay_type: "Stay",
  meals: "Meals",
  stipend_amount: "Stipend",
  stipend_period: "Stipend period",
  deliverables: "Deliverables",
  languages: "Languages",
  min_followers: "Followers",
  min_stay_days: "Minimum stay",
  screening_questions: "Questions",
};

/**
 * The five-step gig builder with a live preview. Drafts save themselves; a gig past
 * draft saves with a button, since some edits send it back to review.
 */
export function GigBuilder({
  initialGig,
  properties,
  skills,
  today,
}: {
  initialGig: Gig | null;
  properties: Property[];
  skills: Skill[];
  /** For tests; defaults to the browser's today. */
  today?: string;
}) {
  const [initialDraft] = useState(() =>
    initialGig
      ? draftFromGig(initialGig)
      : emptyDraft(properties.length === 1 ? properties[0]!.id : ""),
  );
  const [draft, setDraft] = useState<GigDraft>(initialDraft);
  const [step, setStep] = useState<StepId>("basics");
  const [visited, setVisited] = useState<ReadonlySet<StepId>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState("");
  const saver = useGigSaver(initialGig, initialDraft);
  const { gig, state } = saver;
  const status: GigStatus = gig?.status ?? "draft";
  const autosave = status === "draft";
  const heading = useRef<HTMLHeadingElement>(null);

  const shape = useMemo(() => checkShape(draft), [draft]);
  const complete = useMemo(() => checkComplete(draft, today), [draft, today]);
  const property = properties.find((p) => p.id === draft.property);

  // Autosave drafts a moment after the last change.
  const { save, track } = saver;
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    const invalid = Object.keys(shape).length > 0;
    track(draft, invalid);
    if (!autosave || invalid) return;
    const timer = window.setTimeout(() => void save(draft), AUTOSAVE_DELAY_MS);
    return () => window.clearTimeout(timer);
  }, [draft, shape, autosave, save, track]);

  function set(patch: Partial<GigDraft>) {
    setDraft((d) => ({ ...d, ...patch }));
    for (const field of Object.keys(patch)) saver.clearServerError(field);
    setSubmitError("");
  }

  function error(field: GigField): string | undefined {
    return (
      saver.serverErrors[field] ??
      shape[field] ??
      (visited.has(stepOf(field)) ? complete[field] : undefined)
    );
  }

  function goTo(next: StepId) {
    setVisited((v) => new Set([...v, step]));
    setStep(next);
    requestAnimationFrame(() => heading.current?.focus());
  }

  const index = STEPS.findIndex((s) => s.id === step);
  const allProblems: GigErrors = { ...complete, ...saver.serverErrors };
  const reviewedChanged =
    gig && !autosave
      ? REVIEWED_FIELDS.some(
          (f) =>
            JSON.stringify(toPayload(draft)[f]) !== JSON.stringify(toPayload(draftFromGig(gig))[f]),
        )
      : false;

  async function submitForReview() {
    setVisited(new Set(STEPS.map((s) => s.id)));
    if (Object.keys(complete).length) {
      setSubmitError("Fix the items listed above first.");
      return;
    }
    setSubmitting(true);
    setSubmitError("");
    try {
      const saved = await save(draft);
      if (!saved) {
        setSubmitError(
          "Your latest changes didn't save. Fix the highlighted fields and try again.",
        );
        return;
      }
      const result = await unwrap(
        api.POST("/api/v1/gigs/{gig_id}/status/", {
          params: { path: { gig_id: saved.id } },
          body: { status: "in_review" },
        }),
      );
      saver.setGig(result);
    } catch (err) {
      const byField = err instanceof ApiError ? fieldErrors(err) : {};
      if (Object.keys(byField).length) {
        saver.setServerErrors(byField);
        setSubmitError("Fix the items listed above first.");
      } else {
        setSubmitError(describeError(err));
      }
    } finally {
      setSubmitting(false);
    }
  }

  async function saveChanges() {
    const saved = await save(draft);
    if (saved) setDraft(draftFromGig(saved));
  }

  if (gig && !EDITABLE.has(gig.status)) {
    return (
      <div className="page">
        <header className="page__header">
          <Link href="/console/gigs" className="back-link">
            All gigs
          </Link>
          <h1 className="page__title">{gig.title}</h1>
        </header>
        <p className="note">
          This gig is <GigStatusChip status={gig.status} /> and can&apos;t be edited.{" "}
          <Link href={`/console/gigs/${gig.id}/applicants`}>See its applicants</Link>
        </p>
      </div>
    );
  }

  const submitted = gig?.status === "in_review" && initialGig?.status !== "in_review";

  return (
    <div className="page page--wide">
      <header className="page__header">
        <Link href="/console/gigs" className="back-link">
          All gigs
        </Link>
        <div className="page__title-row">
          <h1 className="page__title">{gig ? "Edit gig" : "Post a gig"}</h1>
          {gig ? <GigStatusChip status={gig.status} /> : null}
        </div>
        {gig?.status_reason ? (
          <p className="note note--warning">Our team&apos;s note: {gig.status_reason}</p>
        ) : null}
        <ol className="stepper" aria-label="Steps">
          {STEPS.map((s, i) => {
            const hasProblem = visited.has(s.id) && s.fields.some((f) => allProblems[f]);
            return (
              <li key={s.id}>
                <button
                  type="button"
                  className={`stepper__step${s.id === step ? " stepper__step--current" : ""}`}
                  aria-current={s.id === step ? "step" : undefined}
                  onClick={() => goTo(s.id)}
                >
                  {i + 1} {s.label}
                  {hasProblem ? (
                    <span className="stepper__flag">
                      <span aria-hidden="true">!</span>
                      <span className="visually-hidden"> (needs fixing)</span>
                    </span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ol>
      </header>

      {submitted ? (
        <section className="panel stack" aria-labelledby="submitted-title">
          <h2 id="submitted-title" className="panel__title" tabIndex={-1}>
            Sent for review
          </h2>
          <p>
            We check every gig before it goes live, usually within a day. We&apos;ll let you know if
            anything needs changing.
          </p>
          <div className="actions-row">
            <Link href="/console/gigs" className="button button--primary">
              Back to your gigs
            </Link>
          </div>
        </section>
      ) : (
        <div className="builder">
          <section className="builder__main panel" aria-labelledby="step-title">
            <h2 id="step-title" className="panel__title" ref={heading} tabIndex={-1}>
              {STEPS[index]!.label}
            </h2>
            {step === "basics" ? (
              <BasicsStep
                draft={draft}
                set={set}
                error={error}
                properties={properties}
                skills={skills}
              />
            ) : null}
            {step === "pay" ? <PayStep draft={draft} set={set} error={error} /> : null}
            {step === "who" ? <WhoStep draft={draft} set={set} error={error} /> : null}
            {step === "questions" ? <QuestionsStep draft={draft} set={set} error={error} /> : null}
            {step === "review" ? (
              <ReviewStep draft={draft} problems={allProblems} goTo={goTo} property={property} />
            ) : null}

            {reviewedChanged && (status === "live" || status === "paused") ? (
              <p className="note note--warning">
                You changed the pay, hours or dates. Saving sends this gig back to review, and it
                stops showing to talent until it&apos;s approved.
              </p>
            ) : null}
            {submitError ? (
              <p className="form-error" role="alert">
                {submitError}
              </p>
            ) : null}

            <div className="builder__footer">
              <SaveStatus
                state={
                  !gig && !canCreate(draft) && state.kind !== "invalid"
                    ? { kind: "waiting" }
                    : state
                }
                autosave={autosave}
              />
              <div className="actions-row">
                {index > 0 ? (
                  <Button variant="secondary" onClick={() => goTo(STEPS[index - 1]!.id)}>
                    Back
                  </Button>
                ) : null}
                {!autosave ? (
                  <Button
                    variant="secondary"
                    onClick={() => void saveChanges()}
                    busy={state.kind === "saving"}
                    busyLabel="Saving…"
                    disabled={Object.keys(shape).length > 0}
                  >
                    Save changes
                  </Button>
                ) : null}
                {step !== "review" ? (
                  <Button onClick={() => goTo(STEPS[index + 1]!.id)}>Next</Button>
                ) : status === "draft" ? (
                  <Button
                    onClick={() => void submitForReview()}
                    busy={submitting}
                    busyLabel="Sending…"
                  >
                    Submit for review
                  </Button>
                ) : null}
              </div>
            </div>
          </section>

          <aside className="builder__aside" aria-label="Preview">
            <p className="builder__aside-label">How talent will see it</p>
            <GigPreviewCard
              draft={draft}
              place={property ? `${property.name} · ${property.city}` : ""}
            />
            <p className="note">
              Every gig is checked by our team before it goes live. Gigs with unclear hours, stay or
              meal details are sent back for changes.
            </p>
          </aside>
        </div>
      )}
    </div>
  );
}
