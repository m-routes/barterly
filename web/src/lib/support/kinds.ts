import type { SupportKind } from "@/lib/api/types";

/** What people can write to us about, in the order the form lists them. */
export const SUPPORT_KINDS: ReadonlyArray<{ value: SupportKind; label: string; hint: string }> = [
  { value: "help", label: "Help with something", hint: "We answer within a day." },
  {
    value: "payment",
    label: "Money or payments",
    hint: "Urgent: we answer within 2 hours, 8am to 10pm.",
  },
  {
    value: "safety",
    label: "A safety concern",
    hint: "Urgent: we answer within 2 hours, 8am to 10pm. In danger now? Call 112.",
  },
  { value: "bug", label: "Something isn't working", hint: "We answer within a day." },
  { value: "feedback", label: "Feedback or an idea", hint: "We read every one, within 3 days." },
];

export const STATUS_TEXT: Record<string, string> = {
  open: "Waiting for us",
  waiting: "We've answered",
  resolved: "Resolved",
};
