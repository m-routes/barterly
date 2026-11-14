import type {
  CompensationModel,
  DeliverableType,
  Gig,
  Language,
  Meals,
  RequiredVerification,
  RoleTemplate,
  StayType,
  StipendPeriod,
} from "@/lib/api/types";

/**
 * The gig builder's working copy. Inputs hold text ("" while empty), so a half-typed
 * number never turns into a wrong value; toPayload() converts it for the API.
 */
export type DeliverableDraft = { type: DeliverableType | ""; quantity: string; notes: string };

export type GigDraft = {
  property: string;
  title: string;
  description: string;
  role_template: RoleTemplate | "";
  slots: string;
  start_date: string;
  /** Gigs end on a date or after a number of days, not both. */
  length_mode: "end_date" | "duration";
  end_date: string;
  duration_days: string;
  apply_by: string;
  hours_per_day: string;
  days_per_week: string;
  compensation_model: CompensationModel | "";
  stay_type: StayType | "";
  meals: Meals | "";
  wifi: boolean;
  stipend_amount: string;
  stipend_period: StipendPeriod | "";
  deliverables: DeliverableDraft[];
  skills: string[];
  languages: Language[];
  min_followers: string;
  min_stay_days: string;
  screening_questions: string[];
  required_verification: RequiredVerification;
};

export const STIPEND_MODELS: ReadonlySet<CompensationModel> = new Set(["hybrid", "paid"]);
export const DELIVERABLE_MODELS: ReadonlySet<CompensationModel> = new Set(["barter", "hybrid"]);

/** Mirrors backend apps/gigs/constants.py. */
export const GIG_LIMITS = {
  minAgeYears: 18,
  maxHoursPerDay: 6,
  maxDaysPerWeek: 6,
  maxScreeningQuestions: 5,
  maxQuestionLength: 300,
  maxDeliverables: 10,
  maxDeliverableQuantity: 50,
  maxGigDays: 365,
  maxTitle: 120,
  maxDescription: 5000,
} as const;

export function emptyDraft(propertyId = ""): GigDraft {
  return {
    property: propertyId,
    title: "",
    description: "",
    role_template: "",
    slots: "1",
    start_date: "",
    length_mode: "end_date",
    end_date: "",
    duration_days: "",
    apply_by: "",
    hours_per_day: "",
    days_per_week: "",
    compensation_model: "",
    stay_type: "",
    meals: "",
    wifi: true,
    stipend_amount: "",
    stipend_period: "",
    deliverables: [],
    skills: [],
    languages: [],
    min_followers: "",
    min_stay_days: "",
    screening_questions: [],
    required_verification: "id_verified",
  };
}

const text = (value: number | string | null | undefined) => (value == null ? "" : String(value));

export function draftFromGig(gig: Gig): GigDraft {
  return {
    property: gig.property,
    title: gig.title,
    description: gig.description ?? "",
    role_template: gig.role_template,
    slots: text(gig.slots),
    start_date: text(gig.start_date),
    length_mode: gig.duration_days && !gig.end_date ? "duration" : "end_date",
    end_date: text(gig.end_date),
    duration_days: text(gig.duration_days),
    apply_by: text(gig.apply_by),
    hours_per_day: text(gig.hours_per_day),
    days_per_week: text(gig.days_per_week),
    compensation_model: gig.compensation_model,
    stay_type: gig.stay_type ?? "",
    meals: gig.meals ?? "",
    wifi: gig.wifi ?? false,
    stipend_amount: gig.stipend_amount ? String(Number(gig.stipend_amount)) : "",
    stipend_period: gig.stipend_period ?? "",
    deliverables: (gig.deliverables ?? []).map((d) => ({
      type: d.type,
      quantity: String(d.quantity),
      notes: d.notes ?? "",
    })),
    skills: gig.skills ?? [],
    languages: gig.languages ?? [],
    min_followers: text(gig.min_followers),
    min_stay_days: text(gig.min_stay_days),
    screening_questions: gig.screening_questions ?? [],
    required_verification: gig.required_verification ?? "id_verified",
  };
}

/** A whole number from an input, null when empty, NaN when it isn't one. */
export function wholeNumber(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed === "") return null;
  return /^\d+$/.test(trimmed) ? Number(trimmed) : Number.NaN;
}

/** Rupees: up to 2 decimal places; null when empty, NaN when not a number. */
export function rupees(value: string): number | null {
  const trimmed = value.replace(/[,\s₹]/g, "");
  if (trimmed === "") return null;
  return /^\d+(\.\d{1,2})?$/.test(trimmed) ? Number(trimmed) : Number.NaN;
}

const orNull = (value: string) => (value.trim() === "" ? null : value);
const finite = (n: number | null) => (n != null && Number.isFinite(n) ? n : null);

/**
 * What the API gets. Fields that don't apply to the chosen pay model are cleared
 * (a stipend on a volunteer gig, deliverables on a paid one), as the backend requires.
 */
export function toPayload(draft: GigDraft) {
  const model = draft.compensation_model;
  const stipend = STIPEND_MODELS.has(model as CompensationModel);
  const deliverables = DELIVERABLE_MODELS.has(model as CompensationModel);
  const amount = finite(rupees(draft.stipend_amount));
  return {
    property: draft.property,
    title: draft.title.trim(),
    description: draft.description.trim(),
    role_template: draft.role_template as RoleTemplate,
    compensation_model: model as CompensationModel,
    slots: finite(wholeNumber(draft.slots)) ?? 1,
    start_date: orNull(draft.start_date),
    end_date: draft.length_mode === "end_date" ? orNull(draft.end_date) : null,
    duration_days:
      draft.length_mode === "duration" ? finite(wholeNumber(draft.duration_days)) : null,
    apply_by: orNull(draft.apply_by),
    hours_per_day: finite(wholeNumber(draft.hours_per_day)),
    days_per_week: finite(wholeNumber(draft.days_per_week)),
    stay_type: draft.stay_type,
    meals: draft.meals,
    wifi: draft.wifi,
    stipend_amount: stipend && amount != null ? amount.toFixed(2) : null,
    stipend_period: stipend ? draft.stipend_period : "",
    deliverables: deliverables
      ? draft.deliverables
          .filter((d) => d.type)
          .map((d) => ({
            type: d.type as DeliverableType,
            quantity: finite(wholeNumber(d.quantity)) ?? 0,
            notes: d.notes.trim(),
          }))
      : [],
    skills: draft.skills,
    languages: draft.languages,
    min_followers: finite(wholeNumber(draft.min_followers)),
    min_stay_days: finite(wholeNumber(draft.min_stay_days)),
    screening_questions: draft.screening_questions.map((q) => q.trim()).filter(Boolean),
    required_verification: draft.required_verification,
  };
}

export type GigPayload = ReturnType<typeof toPayload>;

/** The API needs these four before a draft can be saved for the first time. */
export function canCreate(draft: GigDraft): boolean {
  return Boolean(
    draft.property && draft.title.trim() && draft.role_template && draft.compensation_model,
  );
}

/** Edits to these send a live or paused gig back to review (backend REVIEWED_FIELDS). */
export const REVIEWED_FIELDS = [
  "compensation_model",
  "stipend_amount",
  "stipend_period",
  "hours_per_day",
  "days_per_week",
  "start_date",
  "end_date",
  "duration_days",
  "apply_by",
] as const;
