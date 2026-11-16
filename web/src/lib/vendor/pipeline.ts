/**
 * The applicant pipeline's rules, kept pure so they're tested without the DOM.
 *
 * Stages are the canvas's four columns. Applicants only move forward: applied →
 * shortlisted → interview → offered (the backend's transition table refuses the rest).
 * Moving to Offered isn't a status change: it opens the offer builder, and the card
 * moves once the offer is sent.
 */
import type { components } from "@/lib/api/schema";

export type PipelineApplicant = components["schemas"]["VendorApplicationListItem"];
export type FilterParams = components["schemas"]["FilterParams"];

export const STAGES = [
  { status: "applied", label: "Applied" },
  { status: "shortlisted", label: "Shortlisted" },
  { status: "interview", label: "Interview" },
  { status: "offered", label: "Offered" },
] as const;
export type Stage = (typeof STAGES)[number]["status"];
export const STAGE_STATUSES: readonly Stage[] = STAGES.map((s) => s.status);

export function stageLabel(stage: Stage): string {
  return STAGES.find((s) => s.status === stage)!.label;
}

export function isStage(status: string): status is Stage {
  return (STAGE_STATUSES as readonly string[]).includes(status);
}

export type Move =
  | { kind: "status"; to: "shortlisted" | "interview" } // POST .../status/
  | { kind: "offer" } // open the offer builder
  | { kind: "none"; reason: string };

/** What moving a card from one column to another means. */
export function moveFor(from: string, to: Stage): Move {
  if (!isStage(from)) return { kind: "none", reason: "This applicant isn't in the pipeline." };
  const order = STAGE_STATUSES.indexOf(from);
  const target = STAGE_STATUSES.indexOf(to);
  if (target === order) return { kind: "none", reason: `Already in ${stageLabel(to)}.` };
  if (target < order) {
    return { kind: "none", reason: `Applicants can't move back to ${stageLabel(to)}.` };
  }
  if (from === "offered") return { kind: "none", reason: "The offer is out: wait for a reply." };
  if (to === "offered") return { kind: "offer" };
  if (to === "applied") return { kind: "none", reason: "Applicants can't move back to Applied." };
  return { kind: "status", to };
}

/** Columns a card could move to (for the "Move to" menu and keyboard moves). */
export function targetsFor(from: string): Stage[] {
  return STAGE_STATUSES.filter((to) => moveFor(from, to).kind !== "none");
}

/** The board after moving one or more cards (unknown ids are ignored). */
export function withStatus(
  items: readonly PipelineApplicant[],
  ids: ReadonlySet<string> | readonly string[],
  status: PipelineApplicant["status"],
): PipelineApplicant[] {
  const set = ids instanceof Set ? ids : new Set(ids);
  return items.map((a) => (set.has(a.id) ? { ...a, status } : a));
}

export function columns(items: readonly PipelineApplicant[]) {
  return STAGES.map((stage) => ({
    ...stage,
    cards: items.filter((a) => a.status === stage.status),
  }));
}

/** The query for the board: every pipeline stage, with the chosen filters. */
export function listQuery(filters: FilterParams) {
  return {
    status: STAGE_STATUSES.join(","),
    page_size: 100,
    sort: filters.sort ?? "fit",
    ...(filters.min_score ? { min_score: filters.min_score } : {}),
    ...(filters.tag ? { tag: filters.tag } : {}),
    ...(filters.q ? { q: filters.q } : {}),
    ...(filters.badge ? { badge: filters.badge } : {}),
  };
}

/** Filters with empty values dropped, for saving and comparing. */
export function cleanFilters(filters: FilterParams): FilterParams {
  return Object.fromEntries(
    Object.entries(filters).filter(([, v]) => v !== undefined && v !== "" && v !== null),
  ) as FilterParams;
}

export function sameFilters(a: FilterParams, b: FilterParams): boolean {
  const x = cleanFilters({ sort: "fit", ...a });
  const y = cleanFilters({ sort: "fit", ...b });
  const keys = new Set([...Object.keys(x), ...Object.keys(y)]) as Set<keyof FilterParams>;
  return [...keys].every((k) => x[k] === y[k]);
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0]![0]! + (parts.length > 1 ? parts.at(-1)![0]! : "")).toUpperCase();
}

/** The canvas's three avatar tints, picked steadily per person. */
const TINTS = ["#BFE0D6", "#F3D3A6", "#CFCBEF"];
export function tintFor(id: string): string {
  let sum = 0;
  for (const ch of id) sum = (sum + ch.charCodeAt(0)) % 9973;
  return TINTS[sum % TINTS.length]!;
}
