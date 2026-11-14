"use client";

import { useId } from "react";

import { Button } from "@/components/ui/Button";
import { SelectField, TextArea, TextField } from "@/components/ui/fields";
import type {
  CompensationModel,
  DeliverableType,
  Language,
  Meals,
  Property,
  RequiredVerification,
  RoleTemplate,
  Skill,
  StayType,
  StipendPeriod,
} from "@/lib/api/types";
import { DELIVERABLE_MODELS, GIG_LIMITS, STIPEND_MODELS, type GigDraft } from "@/lib/gigs/draft";
import type { GigField } from "@/lib/validation/gig";
import {
  COMPENSATION_MODELS,
  DELIVERABLE_LABELS,
  LANGUAGE_LABELS,
  MEALS_LABELS,
  REQUIRED_VERIFICATION_LABELS,
  ROLE_TEMPLATE_LABELS,
  STAY_TYPE_LABELS,
  STIPEND_PERIOD_LABELS,
  options,
} from "@/lib/vendor/labels";

export type StepProps = {
  draft: GigDraft;
  set: (patch: Partial<GigDraft>) => void;
  error: (field: GigField) => string | undefined;
};

const ROLE_HINTS: Record<RoleTemplate, string> = {
  volunteer: "Reception, kitchen, events or upkeep in exchange for a stay.",
  content_creator: "Reels, posts, videos or photos for your property.",
  trip_leader: "Lead treks, tours or day trips for your guests.",
  specialist: "Yoga, art, music, cooking or another skill you need.",
};

function ErrorText({ id, message }: { id: string; message?: string }) {
  return message ? (
    <p className="field__error" id={id}>
      {message}
    </p>
  ) : null;
}

/** Radio cards (role, pay model, who can apply). */
function ChoiceCards<T extends string>({
  legend,
  name,
  value,
  choices,
  onChange,
  error,
}: {
  legend: string;
  name: string;
  value: T | "";
  choices: { value: T; title: string; text: string }[];
  onChange: (value: T) => void;
  error?: string;
}) {
  const id = useId();
  return (
    <fieldset
      className="choice-group"
      aria-describedby={error ? `${id}-error` : undefined}
      aria-invalid={error ? true : undefined}
    >
      <legend className="field__label choice-group__legend">{legend}</legend>
      {choices.map((choice) => (
        <label
          key={choice.value}
          className={`choice-card${value === choice.value ? " choice-card--selected" : ""}`}
        >
          <input
            className="choice-card__input"
            type="radio"
            name={name}
            value={choice.value}
            checked={value === choice.value}
            onChange={() => onChange(choice.value)}
          />
          <span className="choice-card__title">{choice.title}</span>
          <span className="choice-card__text">{choice.text}</span>
        </label>
      ))}
      <ErrorText id={`${id}-error`} message={error} />
    </fieldset>
  );
}

/** Toggle chips backed by checkboxes (languages, skills). */
function ToggleChips<T extends string>({
  legend,
  hint,
  selected,
  choices,
  onChange,
  error,
}: {
  legend: string;
  hint?: string;
  selected: T[];
  choices: { value: T; label: string }[];
  onChange: (values: T[]) => void;
  error?: string;
}) {
  const id = useId();
  return (
    <fieldset className="toggle-group" aria-describedby={error ? `${id}-error` : undefined}>
      <legend className="field__label">{legend}</legend>
      {hint ? <p className="field__hint">{hint}</p> : null}
      <div className="toggle-group__chips">
        {choices.map((choice) => {
          const on = selected.includes(choice.value);
          return (
            <label key={choice.value} className={`toggle-chip${on ? " toggle-chip--on" : ""}`}>
              <input
                type="checkbox"
                className="toggle-chip__input"
                checked={on}
                onChange={() =>
                  onChange(
                    on ? selected.filter((v) => v !== choice.value) : [...selected, choice.value],
                  )
                }
              />
              {choice.label}
            </label>
          );
        })}
      </div>
      <ErrorText id={`${id}-error`} message={error} />
    </fieldset>
  );
}

export function BasicsStep({
  draft,
  set,
  error,
  properties,
  skills,
}: StepProps & { properties: Property[]; skills: Skill[] }) {
  return (
    <div className="stack">
      <ChoiceCards<RoleTemplate>
        legend="Role"
        name="role_template"
        value={draft.role_template}
        choices={options(ROLE_TEMPLATE_LABELS).map((o) => ({
          value: o.value,
          title: o.label,
          text: ROLE_HINTS[o.value],
        }))}
        onChange={(role_template) => set({ role_template })}
        error={error("role_template")}
      />
      <TextField
        label="Gig title"
        hint="What the talent will do, e.g. Reception and social media volunteer."
        maxLength={GIG_LIMITS.maxTitle}
        value={draft.title}
        onChange={(e) => set({ title: e.target.value })}
        error={error("title")}
      />
      <TextArea
        label="Description"
        hint="The work, a typical day, and what makes your place special."
        rows={6}
        value={draft.description}
        onChange={(e) => set({ description: e.target.value })}
        error={error("description")}
      />
      <div className="form-grid">
        <SelectField
          label="Property"
          options={properties.map((p) => ({ value: p.id, label: `${p.name}, ${p.city}` }))}
          value={draft.property}
          onChange={(e) => set({ property: e.target.value })}
          error={error("property")}
        />
        <TextField
          label="Open slots"
          type="number"
          inputMode="numeric"
          min={1}
          value={draft.slots}
          onChange={(e) => set({ slots: e.target.value })}
          error={error("slots")}
        />
      </div>

      <fieldset className="form-section">
        <legend className="form-section__title">Dates</legend>
        <div className="form-grid">
          <TextField
            label="Start date"
            type="date"
            value={draft.start_date}
            onChange={(e) => set({ start_date: e.target.value })}
            error={error("start_date")}
          />
          <TextField
            label="Apply by"
            type="date"
            hint="Applications close at the end of this day."
            value={draft.apply_by}
            onChange={(e) => set({ apply_by: e.target.value })}
            error={error("apply_by")}
          />
        </div>
        <div className="segmented" role="radiogroup" aria-label="How the gig ends">
          {(
            [
              ["end_date", "Ends on a date"],
              ["duration", "Lasts a number of days"],
            ] as const
          ).map(([mode, label]) => (
            <label
              key={mode}
              className={`segmented__option${draft.length_mode === mode ? " segmented__option--on" : ""}`}
            >
              <input
                type="radio"
                name="length_mode"
                className="segmented__input"
                checked={draft.length_mode === mode}
                onChange={() => set({ length_mode: mode })}
              />
              {label}
            </label>
          ))}
        </div>
        {draft.length_mode === "end_date" ? (
          <TextField
            label="End date"
            type="date"
            value={draft.end_date}
            onChange={(e) => set({ end_date: e.target.value })}
            error={error("end_date")}
          />
        ) : (
          <TextField
            label="Length in days"
            type="number"
            inputMode="numeric"
            min={1}
            max={GIG_LIMITS.maxGigDays}
            value={draft.duration_days}
            onChange={(e) => set({ duration_days: e.target.value })}
            error={error("duration_days")}
          />
        )}
      </fieldset>

      <fieldset className="form-section">
        <legend className="form-section__title">Hours</legend>
        <div className="form-grid">
          <TextField
            label="Hours per day"
            type="number"
            inputMode="numeric"
            min={1}
            max={GIG_LIMITS.maxHoursPerDay}
            hint={`Maximum ${GIG_LIMITS.maxHoursPerDay} hours a day.`}
            value={draft.hours_per_day}
            onChange={(e) => set({ hours_per_day: e.target.value })}
            error={error("hours_per_day")}
          />
          <TextField
            label="Days per week"
            type="number"
            inputMode="numeric"
            min={1}
            max={GIG_LIMITS.maxDaysPerWeek}
            hint="At least one day off a week."
            value={draft.days_per_week}
            onChange={(e) => set({ days_per_week: e.target.value })}
            error={error("days_per_week")}
          />
        </div>
      </fieldset>

      {skills.length ? (
        <ToggleChips
          legend="Skills that help (optional)"
          hint="Talent with these skills rank higher for this gig."
          selected={draft.skills}
          choices={skills.map((s) => ({ value: s.slug, label: s.name }))}
          onChange={(values) => set({ skills: values })}
        />
      ) : null}
    </div>
  );
}

export function PayStep({ draft, set, error }: StepProps) {
  const model = draft.compensation_model as CompensationModel;
  const deliverableId = useId();
  return (
    <div className="stack">
      <ChoiceCards<CompensationModel>
        legend="How does this gig pay?"
        name="compensation_model"
        value={draft.compensation_model}
        choices={(Object.keys(COMPENSATION_MODELS) as CompensationModel[]).map((value) => ({
          value,
          title: COMPENSATION_MODELS[value].title,
          text: COMPENSATION_MODELS[value].text,
        }))}
        onChange={(compensation_model) => set({ compensation_model })}
        error={error("compensation_model")}
      />
      <div className="form-grid">
        <SelectField
          label="Stay"
          options={options(STAY_TYPE_LABELS)}
          value={draft.stay_type}
          onChange={(e) => set({ stay_type: e.target.value as StayType | "" })}
          error={error("stay_type")}
        />
        <SelectField
          label="Meals"
          options={options(MEALS_LABELS)}
          value={draft.meals}
          onChange={(e) => set({ meals: e.target.value as Meals | "" })}
          error={error("meals")}
        />
      </div>
      <label className="checkbox">
        <input
          type="checkbox"
          checked={draft.wifi}
          onChange={(e) => set({ wifi: e.target.checked })}
        />
        Wi-Fi included
      </label>

      {STIPEND_MODELS.has(model) ? (
        <fieldset className="form-section">
          <legend className="form-section__title">Stipend</legend>
          <p className="field__hint">Paid into escrow and released when the work is approved.</p>
          <div className="form-grid">
            <TextField
              label="Amount (₹)"
              inputMode="decimal"
              value={draft.stipend_amount}
              onChange={(e) => set({ stipend_amount: e.target.value })}
              error={error("stipend_amount")}
            />
            <SelectField
              label="Paid"
              options={options(STIPEND_PERIOD_LABELS)}
              value={draft.stipend_period}
              onChange={(e) => set({ stipend_period: e.target.value as StipendPeriod | "" })}
              error={error("stipend_period")}
            />
          </div>
        </fieldset>
      ) : null}

      {DELIVERABLE_MODELS.has(model) ? (
        <fieldset
          className="form-section"
          aria-describedby={error("deliverables") ? `${deliverableId}-error` : undefined}
        >
          <legend className="form-section__title">Deliverables</legend>
          <p className="field__hint">What the talent will create, and how many.</p>
          {draft.deliverables.map((item, index) => (
            <div key={index} className="repeat-row">
              <SelectField
                label={`Deliverable ${index + 1}`}
                options={options(DELIVERABLE_LABELS)}
                value={item.type}
                onChange={(e) => {
                  const next = [...draft.deliverables];
                  next[index] = { ...item, type: e.target.value as DeliverableType | "" };
                  set({ deliverables: next });
                }}
              />
              <TextField
                label="How many"
                type="number"
                inputMode="numeric"
                min={1}
                max={GIG_LIMITS.maxDeliverableQuantity}
                value={item.quantity}
                onChange={(e) => {
                  const next = [...draft.deliverables];
                  next[index] = { ...item, quantity: e.target.value };
                  set({ deliverables: next });
                }}
              />
              <TextField
                label="Notes"
                optional
                maxLength={300}
                value={item.notes}
                onChange={(e) => {
                  const next = [...draft.deliverables];
                  next[index] = { ...item, notes: e.target.value };
                  set({ deliverables: next });
                }}
              />
              <Button
                variant="ghost"
                onClick={() =>
                  set({ deliverables: draft.deliverables.filter((_, i) => i !== index) })
                }
                aria-label={`Remove deliverable ${index + 1}`}
              >
                Remove
              </Button>
            </div>
          ))}
          <ErrorText id={`${deliverableId}-error`} message={error("deliverables")} />
          {draft.deliverables.length < GIG_LIMITS.maxDeliverables ? (
            <div>
              <Button
                variant="secondary"
                onClick={() =>
                  set({
                    deliverables: [...draft.deliverables, { type: "", quantity: "1", notes: "" }],
                  })
                }
              >
                Add a deliverable
              </Button>
            </div>
          ) : null}
        </fieldset>
      ) : null}
    </div>
  );
}

export function WhoStep({ draft, set, error }: StepProps) {
  return (
    <div className="stack">
      <p className="note">
        Applicants must be {GIG_LIMITS.minAgeYears} or older on the start date. This applies to
        every gig.
      </p>
      <ChoiceCards<RequiredVerification>
        legend="Verification needed to apply"
        name="required_verification"
        value={draft.required_verification}
        choices={(["id_verified", "trusted_member", "none"] as const).map((value) => ({
          value,
          ...REQUIRED_VERIFICATION_LABELS[value],
        }))}
        onChange={(required_verification) => set({ required_verification })}
      />
      <ToggleChips<Language>
        legend="Languages (optional)"
        hint="Applicants must speak at least one. Leave empty for any language."
        selected={draft.languages}
        choices={options(LANGUAGE_LABELS)}
        onChange={(languages) => set({ languages })}
        error={error("languages")}
      />
      <div className="form-grid">
        <TextField
          label="Minimum stay in days"
          optional
          type="number"
          inputMode="numeric"
          min={0}
          value={draft.min_stay_days}
          onChange={(e) => set({ min_stay_days: e.target.value })}
          error={error("min_stay_days")}
        />
        <TextField
          label="Minimum Instagram followers"
          optional
          type="number"
          inputMode="numeric"
          min={0}
          hint="For content gigs. Leave empty for no minimum."
          value={draft.min_followers}
          onChange={(e) => set({ min_followers: e.target.value })}
          error={error("min_followers")}
        />
      </div>
    </div>
  );
}

export function QuestionsStep({ draft, set, error }: StepProps) {
  const id = useId();
  const questions = draft.screening_questions;
  return (
    <fieldset
      className="stack"
      aria-describedby={error("screening_questions") ? `${id}-error` : undefined}
    >
      <legend className="visually-hidden">Questions for applicants</legend>
      <p className="field__hint">
        Optional. Up to {GIG_LIMITS.maxScreeningQuestions} questions every applicant answers.
      </p>
      {questions.map((question, index) => (
        <div key={index} className="repeat-row repeat-row--question">
          <TextField
            label={`Question ${index + 1}`}
            maxLength={GIG_LIMITS.maxQuestionLength}
            value={question}
            onChange={(e) => {
              const next = [...questions];
              next[index] = e.target.value;
              set({ screening_questions: next });
            }}
          />
          <Button
            variant="ghost"
            onClick={() => set({ screening_questions: questions.filter((_, i) => i !== index) })}
            aria-label={`Remove question ${index + 1}`}
          >
            Remove
          </Button>
        </div>
      ))}
      <ErrorText id={`${id}-error`} message={error("screening_questions")} />
      {questions.length < GIG_LIMITS.maxScreeningQuestions ? (
        <div>
          <Button
            variant="secondary"
            onClick={() => set({ screening_questions: [...questions, ""] })}
          >
            Add a question
          </Button>
        </div>
      ) : null}
    </fieldset>
  );
}
