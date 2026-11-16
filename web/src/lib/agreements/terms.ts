/**
 * How offer and agreement terms read on screen. The terms themselves are the API's
 * (apps/offers/terms.py); this only labels them.
 */
import type {
  AgreementVersion,
  CancellationPolicy,
  OfferStatus,
  Terms,
  UsageScope,
} from "@/lib/api/types";
import { formatDate } from "@/lib/format";
import {
  COMPENSATION_MODELS,
  DELIVERABLE_LABELS,
  MEALS_LABELS,
  STAY_TYPE_LABELS,
  STIPEND_PERIOD_LABELS,
} from "@/lib/vendor/labels";

export const CANCELLATION_LABELS: Record<CancellationPolicy, string> = {
  flexible: "Flexible: free to cancel up to 3 days before",
  moderate: "Moderate: free to cancel up to 7 days before",
  strict: "Strict: free to cancel up to 14 days before",
};

export const USAGE_SCOPE_LABELS: Record<UsageScope, string> = {
  organic: "Your own social channels and website",
  organic_and_ads: "Own channels, website and paid ads",
};

export const OFFER_STATUS_LABELS: Record<OfferStatus, string> = {
  open: "Waiting for an answer",
  accepted: "Accepted",
  declined: "Declined",
  countered: "Change asked for",
  lapsed: "Lapsed",
};

export const VERSION_STATUS_LABELS: Record<AgreementVersion["status"], string> = {
  awaiting: "Waiting for signatures",
  active: "In force",
  superseded: "Replaced",
  declined: "Change declined",
  voided: "Replaced before signing",
};

/** Field names as the API sends them in changed_fields, in words. */
export const TERM_LABELS: Record<string, string> = {
  start_date: "Arrive",
  end_date: "Leave",
  hours_per_day: "Hours a day",
  days_per_week: "Days a week",
  stay_type: "Stay",
  meals: "Meals",
  stipend_amount: "Stipend",
  stipend_period: "Stipend covers",
  deliverables: "Deliverables",
  usage_rights: "Content use",
  cancellation_policy: "Cancellation",
};

export function inr(amount: string | null | undefined): string {
  if (amount == null || amount === "") return "";
  return `₹${Number(amount).toLocaleString("en-IN", { maximumFractionDigits: 2 })}`;
}

/** [field, label, value] rows, in the order people read an offer. */
export function termRows(terms: Terms): Array<[string, string, string]> {
  const rows: Array<[string, string, string]> = [
    ["start_date", "Arrive", formatDate(terms.start_date)],
    ["end_date", "Leave", formatDate(terms.end_date)],
    [
      "hours_per_day",
      "Hours",
      `${terms.hours_per_day} a day, ${terms.days_per_week} days a week (at most ${
        terms.hours_per_day * terms.days_per_week
      } a week)`,
    ],
    ["stay_type", "Stay", STAY_TYPE_LABELS[terms.stay_type]],
    ["meals", "Meals", MEALS_LABELS[terms.meals]],
    [
      "compensation_model",
      "Arrangement",
      `${COMPENSATION_MODELS[terms.compensation_model].badge}: ${COMPENSATION_MODELS[
        terms.compensation_model
      ].title.toLowerCase()}`,
    ],
  ];
  if (terms.stipend_amount) {
    const period = terms.stipend_period ? STIPEND_PERIOD_LABELS[terms.stipend_period] : "";
    rows.push([
      "stipend_amount",
      "Stipend",
      `${inr(terms.stipend_amount)} ${period.toLowerCase()}`.trim(),
    ]);
  }
  if (terms.deliverables?.length) {
    rows.push([
      "deliverables",
      "Deliverables",
      terms.deliverables
        .map(
          (d) => `${d.quantity} × ${DELIVERABLE_LABELS[d.type]}${d.notes ? ` (${d.notes})` : ""}`,
        )
        .join(", "),
    ]);
  }
  if (terms.usage_rights) {
    const u = terms.usage_rights;
    rows.push([
      "usage_rights",
      "Content use",
      `${USAGE_SCOPE_LABELS[u.scope]}, for ${u.duration_months} months${
        u.credit_required ? ", with credit" : ""
      }`,
    ]);
  }
  rows.push([
    "cancellation_policy",
    "Cancellation",
    CANCELLATION_LABELS[terms.cancellation_policy],
  ]);
  return rows;
}

/** The fields a row stands for, so a change to days_per_week highlights the hours row. */
export function rowChanged(field: string, changed: readonly string[]): boolean {
  if (field === "hours_per_day")
    return changed.includes(field) || changed.includes("days_per_week");
  if (field === "stipend_amount")
    return changed.includes(field) || changed.includes("stipend_period");
  return changed.includes(field);
}
