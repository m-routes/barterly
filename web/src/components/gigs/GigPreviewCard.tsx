import type { CompensationModel } from "@/lib/api/types";
import { STIPEND_MODELS, rupees, wholeNumber, type GigDraft } from "@/lib/gigs/draft";
import { COMPENSATION_MODELS, MEALS_LABELS, STAY_TYPE_LABELS } from "@/lib/vendor/labels";

const PERIOD_SUFFIX = { total: "", per_week: "/week", per_month: "/month" } as const;

function formatDay(iso: string): string {
  const date = new Date(`${iso}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? ""
    : date.toLocaleDateString("en-IN", { day: "numeric", month: "short" });
}

/** The card's one-line terms, e.g. "4 hrs/day · 5 days/week · dorm bed + meals". */
export function gigTerms(draft: GigDraft): string {
  const parts: string[] = [];
  const hours = wholeNumber(draft.hours_per_day);
  const days = wholeNumber(draft.days_per_week);
  if (hours) parts.push(`${hours} hrs/day`);
  if (days) parts.push(`${days} days/week`);
  const stay =
    draft.stay_type && draft.stay_type !== "none" ? STAY_TYPE_LABELS[draft.stay_type] : "";
  const meals =
    draft.meals && draft.meals !== "none" ? MEALS_LABELS[draft.meals].toLowerCase() : "";
  if (stay || meals) parts.push([stay.toLowerCase(), meals].filter(Boolean).join(" + "));
  const amount = rupees(draft.stipend_amount);
  if (STIPEND_MODELS.has(draft.compensation_model as CompensationModel) && amount) {
    const period = draft.stipend_period ? PERIOD_SUFFIX[draft.stipend_period] : "";
    parts.push(`₹${amount.toLocaleString("en-IN")}${period} stipend`);
  }
  const deliverables = draft.deliverables.filter((d) => d.type).length;
  if (deliverables) parts.push(`${deliverables} deliverable${deliverables === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

export function gigWhen(draft: GigDraft): string {
  const parts: string[] = [];
  if (draft.start_date) parts.push(`From ${formatDay(draft.start_date)}`);
  const slots = wholeNumber(draft.slots);
  if (slots) parts.push(`${slots} slot${slots === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

/**
 * How the gig will look to talent in Discover, from the builder's working copy
 * (the card layout from the design canvas).
 */
export function GigPreviewCard({ draft, place }: { draft: GigDraft; place: string }) {
  const model = draft.compensation_model || null;
  const terms = gigTerms(draft);
  const when = gigWhen(draft);
  return (
    <article className="gig-card" aria-label="Preview of your gig">
      <div className={`gig-card__hero gig-card__hero--${model ?? "none"}`}>
        <svg viewBox="0 0 350 96" preserveAspectRatio="none" aria-hidden="true">
          <path
            d="M0 96V62l50-34 42 30 56-42 60 46 52-30 90 34v30z"
            fill="#FFFFFF"
            fillOpacity="0.45"
          />
          <path d="M0 96V78l64-26 56 24 70-36 90 38v18z" fill="#FFFFFF" fillOpacity="0.6" />
        </svg>
        {model ? (
          <span className={`gig-card__badge gig-card__badge--${model}`}>
            {COMPENSATION_MODELS[model].badge}
          </span>
        ) : null}
      </div>
      <div className="gig-card__body">
        <h3 className="gig-card__title">{draft.title.trim() || "Your gig title"}</h3>
        <p className="gig-card__muted">{place || "Your property"}</p>
        <p>{terms || "Hours, stay and meals show here"}</p>
        <p className="gig-card__muted">{when || "Start date and slots show here"}</p>
      </div>
    </article>
  );
}
