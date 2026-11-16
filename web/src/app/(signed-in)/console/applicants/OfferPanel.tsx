"use client";

import Link from "next/link";
import { useState } from "react";

import { TermsSummary } from "@/components/agreements/TermsSummary";
import { Button } from "@/components/ui/Button";
import { Chip } from "@/components/ui/StatusChip";
import { FormError, SelectField, TextArea, TextField } from "@/components/ui/fields";
import { ErrorState, LoadingState } from "@/components/ui/states";
import {
  CANCELLATION_LABELS,
  OFFER_STATUS_LABELS,
  USAGE_SCOPE_LABELS,
} from "@/lib/agreements/terms";
import { api, unwrap } from "@/lib/api/client";
import { ApiError, describeError, fieldErrors } from "@/lib/api/errors";
import type { Application, Offer, Terms } from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import { useLoad } from "@/lib/hooks/useLoad";
import { DELIVERABLE_LABELS, MEALS_LABELS, STAY_TYPE_LABELS, options } from "@/lib/vendor/labels";

const CAN_OFFER: ReadonlyArray<Application["status"]> = ["applied", "shortlisted", "interview"];

/** The offer for one applicant: make it, follow it, and answer a counter. */
export function OfferPanel({
  application,
  onChange,
}: {
  application: Application;
  onChange: () => void;
}) {
  const { state, reload } = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/applications/{application_id}/offers/", {
          params: { path: { application_id: application.id } },
        }),
      ),
    `${application.id}:${application.status}`,
  );
  const [making, setMaking] = useState(false);

  function changed() {
    setMaking(false);
    void reload();
    onChange();
  }

  if (state.status === "loading") return <LoadingState label="Loading the offer…" />;
  if (state.status === "error") {
    return (
      <ErrorState
        title="We couldn't load the offer"
        description={describeError(state.error)}
        retry={() => void reload()}
      />
    );
  }
  const thread = state.data;
  const offers = [...thread.offers].reverse();

  return (
    <section className="panel stack-sm" aria-labelledby="offer-title">
      <div className="panel__header panel__header--row">
        <h2 id="offer-title" className="panel__title">
          Offer
        </h2>
        {thread.offer_expires_at ? (
          <span className="field__hint">Answer due {formatDate(thread.offer_expires_at)}</span>
        ) : null}
      </div>

      {offers.length === 0 ? (
        CAN_OFFER.includes(application.status) ? (
          making ? (
            <OfferForm
              applicationId={application.id}
              onSent={changed}
              onCancel={() => setMaking(false)}
            />
          ) : (
            <div className="stack-sm">
              <p>
                Send the terms: dates, hours, stay and what you give in return. They&apos;re fixed
                once sent; {application.applicant.display_name} can accept, decline or ask for one
                change.
              </p>
              <div>
                <Button onClick={() => setMaking(true)}>Make an offer</Button>
              </div>
            </div>
          )
        ) : (
          <p className="field__hint">No offer was made.</p>
        )
      ) : (
        <ol className="offer-thread">
          {offers.map((offer) => (
            <OfferCard
              key={offer.id}
              offer={offer}
              answerable={thread.your_turn && offer.id === thread.open_offer}
              onAnswered={changed}
            />
          ))}
        </ol>
      )}

      {application.status === "confirmed" ? (
        <p className="note">
          Booked. Both of you now sign the agreement:{" "}
          <Link href="/console/agreements">open Agreements</Link>.
        </p>
      ) : null}
    </section>
  );
}

function OfferCard({
  offer,
  answerable,
  onAnswered,
}: {
  offer: Offer;
  answerable: boolean;
  onAnswered: () => void;
}) {
  const [busy, setBusy] = useState<"accept" | "decline" | null>(null);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const isCounter = offer.proposed_by === "talent";
  const title = isCounter
    ? "They asked for a change"
    : offer.revision === 1
      ? "Your offer"
      : "Your final offer";

  async function answer(kind: "accept" | "decline") {
    setBusy(kind);
    setError("");
    try {
      const path = { params: { path: { offer_id: offer.id } } };
      if (kind === "accept") await unwrap(api.POST("/api/v1/offers/{offer_id}/accept/", path));
      else
        await unwrap(api.POST("/api/v1/offers/{offer_id}/decline/", { ...path, body: { reason } }));
      onAnswered();
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(null);
    }
  }

  return (
    <li className="offer-card stack-sm">
      <div className="panel__header panel__header--row">
        <h3 className="offer-card__title">{title}</h3>
        <Chip tone={offer.status === "accepted" ? "success" : "neutral"}>
          {OFFER_STATUS_LABELS[offer.status]}
        </Chip>
      </div>
      {offer.message ? <p className="prewrap offer-card__message">“{offer.message}”</p> : null}
      <TermsSummary terms={offer.terms} changed={offer.changed_fields} />
      {answerable ? (
        <div className="stack-sm">
          <p>
            Accepting books them on these terms. Declining sends your original offer back as a final
            offer they can only accept or decline.
          </p>
          <TextArea
            label="Message if you decline"
            optional
            maxLength={500}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <FormError message={error} />
          <div className="actions-row">
            <Button
              busy={busy === "accept"}
              disabled={!!busy}
              onClick={() => void answer("accept")}
            >
              Accept the change
            </Button>
            <Button
              variant="secondary"
              busy={busy === "decline"}
              disabled={!!busy}
              onClick={() => void answer("decline")}
            >
              Keep my offer
            </Button>
          </div>
        </div>
      ) : null}
    </li>
  );
}

type Draft = Terms;

export function OfferForm({
  applicationId,
  onSent,
  onCancel,
}: {
  applicationId: string;
  onSent: () => void;
  onCancel: () => void;
}) {
  const { state } = useLoad(
    () =>
      unwrap(
        api.GET("/api/v1/applications/{application_id}/offer-draft/", {
          params: { path: { application_id: applicationId } },
        }),
      ),
    applicationId,
  );
  if (state.status === "loading") return <LoadingState label="Preparing the terms…" />;
  if (state.status === "error") {
    return (
      <ErrorState title="We couldn't prepare the terms" description={describeError(state.error)} />
    );
  }
  return (
    <OfferFields
      initial={state.data}
      applicationId={applicationId}
      onSent={onSent}
      onCancel={onCancel}
    />
  );
}

function OfferFields({
  initial,
  applicationId,
  onSent,
  onCancel,
}: {
  initial: Draft;
  applicationId: string;
  onSent: () => void;
  onCancel: () => void;
}) {
  const [terms, setTerms] = useState<Draft>(initial);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) =>
    setTerms((t) => ({ ...t, [key]: value }));

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    setErrors({});
    try {
      await unwrap(
        api.POST("/api/v1/applications/{application_id}/offer/", {
          params: { path: { application_id: applicationId } },
          body: { terms, message },
        }),
      );
      onSent();
    } catch (err) {
      if (err instanceof ApiError && err.isValidation) setErrors(fieldErrors(err));
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="offer-builder">
      <form className="stack-sm offer-form" onSubmit={(e) => void submit(e)} noValidate>
        <div className="form-grid form-grid--two">
          <TextField
            label="Arrive"
            type="date"
            value={terms.start_date}
            error={errors.start_date}
            onChange={(e) => set("start_date", e.target.value)}
          />
          <TextField
            label="Leave"
            type="date"
            value={terms.end_date}
            error={errors.end_date}
            onChange={(e) => set("end_date", e.target.value)}
          />
          <TextField
            label="Hours a day"
            type="number"
            min={1}
            max={6}
            hint="At most 6."
            value={terms.hours_per_day}
            error={errors.hours_per_day}
            onChange={(e) => set("hours_per_day", Number(e.target.value))}
          />
          <TextField
            label="Days a week"
            type="number"
            min={1}
            max={6}
            hint="At least one day off."
            value={terms.days_per_week}
            error={errors.days_per_week}
            onChange={(e) => set("days_per_week", Number(e.target.value))}
          />
          <SelectField
            label="Stay"
            options={options(STAY_TYPE_LABELS)}
            value={terms.stay_type}
            error={errors.stay_type}
            onChange={(e) => set("stay_type", e.target.value as Draft["stay_type"])}
          />
          <SelectField
            label="Meals"
            options={options(MEALS_LABELS)}
            value={terms.meals}
            error={errors.meals}
            onChange={(e) => set("meals", e.target.value as Draft["meals"])}
          />
          {terms.stipend_amount != null ? (
            <TextField
              label="Stipend (₹)"
              type="number"
              min={1}
              hint="As in the gig; change it for this person if you need to."
              value={terms.stipend_amount}
              error={errors.stipend_amount}
              onChange={(e) => set("stipend_amount", e.target.value)}
            />
          ) : null}
          <SelectField
            label="Cancellation"
            options={options(CANCELLATION_LABELS)}
            value={terms.cancellation_policy}
            error={errors.cancellation_policy}
            onChange={(e) =>
              set("cancellation_policy", e.target.value as Draft["cancellation_policy"])
            }
          />
        </div>

        {terms.deliverables?.length ? (
          <fieldset className="stack-sm">
            <legend className="field__label">Deliverables</legend>
            {terms.deliverables.map((d, index) => (
              <TextField
                key={`${d.type}-${index}`}
                label={DELIVERABLE_LABELS[d.type]}
                type="number"
                min={1}
                max={50}
                value={d.quantity}
                onChange={(e) =>
                  set(
                    "deliverables",
                    terms.deliverables!.map((item, i) =>
                      i === index ? { ...item, quantity: Number(e.target.value) } : item,
                    ),
                  )
                }
              />
            ))}
            {errors.deliverables ? <p className="field__error">{errors.deliverables}</p> : null}
          </fieldset>
        ) : null}

        {terms.usage_rights ? (
          <fieldset className="stack-sm">
            <legend className="field__label">How you may use their content</legend>
            <div className="form-grid form-grid--two">
              <SelectField
                label="Where"
                options={options(USAGE_SCOPE_LABELS)}
                value={terms.usage_rights.scope}
                onChange={(e) =>
                  set("usage_rights", {
                    ...terms.usage_rights!,
                    scope: e.target.value as NonNullable<Draft["usage_rights"]>["scope"],
                  })
                }
              />
              <TextField
                label="For how many months"
                type="number"
                min={1}
                max={36}
                value={terms.usage_rights.duration_months}
                onChange={(e) =>
                  set("usage_rights", {
                    ...terms.usage_rights!,
                    duration_months: Number(e.target.value),
                  })
                }
              />
            </div>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={terms.usage_rights.credit_required}
                onChange={(e) =>
                  set("usage_rights", { ...terms.usage_rights!, credit_required: e.target.checked })
                }
              />{" "}
              Credit them when you use it
            </label>
            {errors.usage_rights ? <p className="field__error">{errors.usage_rights}</p> : null}
          </fieldset>
        ) : null}

        <TextArea
          label="Message"
          optional
          maxLength={1000}
          value={message}
          onChange={(e) => setMessage(e.target.value)}
        />
        <p className="note">
          These terms become the agreement you both sign if they accept. Its legal text is still a
          placeholder that a lawyer must review before launch.
        </p>
        <FormError message={error} />
        <div className="actions-row">
          <Button type="submit" busy={busy}>
            Send offer
          </Button>
          <Button variant="ghost" onClick={onCancel} disabled={busy}>
            Cancel
          </Button>
        </div>
      </form>
      <aside className="offer-preview" aria-labelledby="offer-preview-title">
        <h3 id="offer-preview-title" className="panel__title">
          What they&apos;ll see
        </h3>
        <p className="field__hint">Updates as you edit. These become the agreement if accepted.</p>
        <TermsSummary terms={terms} />
      </aside>
    </div>
  );
}
