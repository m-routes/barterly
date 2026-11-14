import {
  DELIVERABLE_MODELS,
  GIG_LIMITS as L,
  STIPEND_MODELS,
  rupees,
  wholeNumber,
  type GigDraft,
} from "@/lib/gigs/draft";
import type { CompensationModel } from "@/lib/api/types";

/**
 * The backend's gig rules (apps/gigs/rules.py), run in the browser so the builder can
 * explain problems as they happen. The messages match the API's, so an error looks
 * the same whether it came from here or from the server. The server still decides.
 *
 * - checkShape: holds for every save, drafts included: what's filled in must make sense.
 * - checkComplete: also holds before a gig can be sent for review.
 */

export type GigErrors = Partial<Record<GigField, string>>;
export type GigField =
  | "property"
  | "title"
  | "description"
  | "role_template"
  | "compensation_model"
  | "slots"
  | "start_date"
  | "end_date"
  | "duration_days"
  | "apply_by"
  | "hours_per_day"
  | "days_per_week"
  | "stay_type"
  | "meals"
  | "stipend_amount"
  | "stipend_period"
  | "deliverables"
  | "languages"
  | "min_followers"
  | "min_stay_days"
  | "screening_questions";

const WHOLE = "Enter a whole number.";

/** Today as YYYY-MM-DD in the browser's time zone. */
export function todayIso(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function daysBetween(start: string, end: string): number {
  return Math.round((Date.parse(end) - Date.parse(start)) / 86_400_000);
}

/** The gig's length in days, when it can be worked out. */
export function gigLengthDays(draft: GigDraft): number | null {
  const duration = wholeNumber(draft.duration_days);
  if (draft.length_mode === "duration" && duration) return duration;
  if (draft.length_mode === "end_date" && draft.start_date && draft.end_date) {
    return daysBetween(draft.start_date, draft.end_date);
  }
  return null;
}

export function checkShape(draft: GigDraft): GigErrors {
  const errors: GigErrors = {};
  const add = (field: GigField, message: string) => {
    errors[field] ??= message;
  };
  const model = draft.compensation_model as CompensationModel;

  if (draft.title.trim().length > L.maxTitle)
    add("title", `Keep the title under ${L.maxTitle} characters.`);
  if (draft.description.length > L.maxDescription) {
    add("description", `Keep the description under ${L.maxDescription} characters.`);
  }

  const slots = wholeNumber(draft.slots);
  if (Number.isNaN(slots)) add("slots", WHOLE);
  else if (slots != null && slots < 1) add("slots", "At least 1 slot.");

  const hours = wholeNumber(draft.hours_per_day);
  if (Number.isNaN(hours)) add("hours_per_day", WHOLE);
  else if (hours != null && !(hours >= 1 && hours <= L.maxHoursPerDay)) {
    add("hours_per_day", `At most ${L.maxHoursPerDay} hours a day.`);
  }

  const days = wholeNumber(draft.days_per_week);
  if (Number.isNaN(days)) add("days_per_week", WHOLE);
  else if (days != null && !(days >= 1 && days <= L.maxDaysPerWeek)) {
    add("days_per_week", "Give at least one day off a week (at most 6 working days).");
  }

  if (STIPEND_MODELS.has(model)) {
    const amount = rupees(draft.stipend_amount);
    if (Number.isNaN(amount)) add("stipend_amount", "Enter an amount in rupees, e.g. 6000.");
    else if (amount != null && amount <= 0)
      add("stipend_amount", "The stipend must be more than zero.");
  }

  if (DELIVERABLE_MODELS.has(model) && draft.deliverables.length) {
    if (draft.deliverables.length > L.maxDeliverables) {
      add("deliverables", `Send a list of at most ${L.maxDeliverables} deliverables.`);
    } else if (
      draft.deliverables.some((d) => {
        const quantity = wholeNumber(d.quantity);
        return (
          !d.type ||
          quantity == null ||
          Number.isNaN(quantity) ||
          quantity < 1 ||
          quantity > L.maxDeliverableQuantity ||
          d.notes.length > 300
        );
      })
    ) {
      add(
        "deliverables",
        "Each deliverable needs a known type, a quantity from 1 to 50 and short notes.",
      );
    }
  }

  const questions = draft.screening_questions;
  if (
    questions.length > L.maxScreeningQuestions ||
    questions.some((q) => q.trim().length > L.maxQuestionLength)
  ) {
    add(
      "screening_questions",
      `At most ${L.maxScreeningQuestions} questions of up to ${L.maxQuestionLength} characters.`,
    );
  }

  const end = draft.length_mode === "end_date" ? draft.end_date : "";
  if (draft.start_date && end && end <= draft.start_date) {
    add("end_date", "The end date must be after the start date.");
  }
  if (draft.length_mode === "duration") {
    const duration = wholeNumber(draft.duration_days);
    if (Number.isNaN(duration)) add("duration_days", WHOLE);
    else if (duration != null && !(duration >= 1 && duration <= L.maxGigDays)) {
      add("duration_days", `Between 1 and ${L.maxGigDays} days.`);
    }
  }
  if (draft.apply_by && draft.start_date && draft.apply_by > draft.start_date) {
    add("apply_by", "Applications must close on or before the start date.");
  }

  const minStay = wholeNumber(draft.min_stay_days);
  const length = gigLengthDays(draft);
  if (Number.isNaN(minStay)) add("min_stay_days", WHOLE);
  else if (minStay != null && length != null && minStay > length) {
    add("min_stay_days", "The minimum stay can't be longer than the gig.");
  }
  if (Number.isNaN(wholeNumber(draft.min_followers))) add("min_followers", WHOLE);
  return errors;
}

const REQUIRED = "Required before the gig can be reviewed.";

export function checkComplete(draft: GigDraft, today = todayIso()): GigErrors {
  const errors: GigErrors = {};
  const add = (field: GigField, message: string) => {
    errors[field] ??= message;
  };
  // Shape problems first: they're the more specific message for a field.
  Object.assign(errors, checkShape(draft));

  if (!draft.property) add("property", "Choose the property this gig is at.");
  if (!draft.role_template) add("role_template", "Choose a role.");
  if (!draft.compensation_model) add("compensation_model", "Choose a pay model.");
  const required: [GigField, unknown][] = [
    ["title", draft.title.trim()],
    ["description", draft.description.trim()],
    ["start_date", draft.start_date],
    ["apply_by", draft.apply_by],
    ["hours_per_day", draft.hours_per_day.trim()],
    ["days_per_week", draft.days_per_week.trim()],
    ["stay_type", draft.stay_type],
    ["meals", draft.meals],
  ];
  for (const [field, value] of required) if (!value) add(field, REQUIRED);

  const hasEnd =
    draft.length_mode === "end_date"
      ? Boolean(draft.end_date)
      : Boolean(draft.duration_days.trim());
  if (!hasEnd) {
    add(
      draft.length_mode === "end_date" ? "end_date" : "duration_days",
      "Give an end date or a duration.",
    );
  }
  if (draft.start_date && draft.start_date <= today)
    add("start_date", "The start date must be in the future.");
  if (draft.apply_by && draft.apply_by < today) add("apply_by", "The apply-by date has passed.");

  const model = draft.compensation_model;
  const noStay = draft.stay_type === "" || draft.stay_type === "none";
  if (model === "volunteer") {
    if (noStay) add("stay_type", "Volunteer gigs must say where volunteers stay.");
    if (!draft.meals) add("meals", "Volunteer gigs must say which meals are included.");
  }
  if (model === "barter" && !draft.deliverables.some((d) => d.type)) {
    add("deliverables", "Barter gigs need at least one deliverable.");
  }
  if (model === "hybrid" || model === "paid") {
    const amount = rupees(draft.stipend_amount);
    if (!amount || amount <= 0)
      add("stipend_amount", "Hybrid and paid gigs need a stipend above zero.");
    if (!draft.stipend_period) {
      add("stipend_period", "Say whether the stipend is per week, per month or total.");
    }
  }
  if (model === "hybrid" && noStay) add("stay_type", "Hybrid gigs include a stay: say what kind.");
  return errors;
}

export type StepId = "basics" | "pay" | "who" | "questions" | "review";

export const STEPS: { id: StepId; label: string; fields: GigField[] }[] = [
  {
    id: "basics",
    label: "Basics",
    fields: [
      "role_template",
      "title",
      "description",
      "property",
      "slots",
      "start_date",
      "end_date",
      "duration_days",
      "apply_by",
      "hours_per_day",
      "days_per_week",
    ],
  },
  {
    id: "pay",
    label: "Pay model",
    fields: [
      "compensation_model",
      "stay_type",
      "meals",
      "stipend_amount",
      "stipend_period",
      "deliverables",
    ],
  },
  { id: "who", label: "Who can apply", fields: ["languages", "min_followers", "min_stay_days"] },
  { id: "questions", label: "Questions", fields: ["screening_questions"] },
  { id: "review", label: "Review", fields: [] },
];

export function stepOf(field: string): StepId {
  return STEPS.find((s) => (s.fields as string[]).includes(field))?.id ?? "review";
}
