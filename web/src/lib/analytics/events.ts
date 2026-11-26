/**
 * The product events the web may send. The server keeps only these, with only the listed
 * properties (backend/apps/analytics/events.py; a backend test compares the lists).
 * Never put free text or personal details in a property.
 */
export const EVENT_NAMES = [
  "screen_view",
  "onboarding_step",
  "invite_entered",
  "gig_builder_step",
  "gig_submitted",
  "search",
  "gig_viewed",
  "apply_started",
  "apply_submitted",
  "offer_viewed",
  "help_opened",
  "feedback_sent",
] as const;

export type EventName = (typeof EVENT_NAMES)[number];

export type EventProps = {
  screen_view: { screen: string };
  onboarding_step: { step: "role" | "consent" | "profile" | "property" | "done" };
  invite_entered: { ok: boolean };
  gig_builder_step: { step: number };
  gig_submitted: { gig_id: string };
  search: { filters: number; results: number };
  gig_viewed: { gig_id: string; source?: "search" | "alert" | "saved" | "link" | "home" };
  apply_started: { gig_id: string };
  apply_submitted: { gig_id: string; offline?: boolean };
  offer_viewed: { application_id: string };
  help_opened: { screen: string };
  feedback_sent: { kind: "help" | "feedback" | "bug" | "safety" | "payment" };
};

const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** A path as a screen name, with ids taken out: /console/gigs/<uuid>/edit → console/gigs/edit. */
export function screenOf(pathname: string): string {
  const parts = pathname
    .split("/")
    .filter((part) => part && !ID.test(part) && !/^\d+$/.test(part))
    .map((part) => part.toLowerCase().replace(/[^a-z0-9_-]/g, ""))
    .filter(Boolean);
  return (parts.join("/") || "home").slice(0, 60);
}
