import type { ApplicationStatus, GigStatus, VerificationStatus } from "@/lib/api/types";
import {
  APPLICATION_STATUS_LABELS,
  GIG_STATUS_LABELS,
  VERIFICATION_STATUS_LABELS,
} from "@/lib/vendor/labels";

export type ChipTone = "neutral" | "pending" | "success" | "warning" | "danger" | "dark";

/** A small rounded label. Colour is never the only signal: the text names the state. */
export function Chip({
  tone = "neutral",
  children,
}: {
  tone?: ChipTone;
  children: React.ReactNode;
}) {
  return <span className={`chip chip--${tone}`}>{children}</span>;
}

const GIG_TONES: Record<GigStatus, ChipTone> = {
  draft: "dark",
  in_review: "pending",
  live: "success",
  paused: "warning",
  filled: "success",
  closed: "neutral",
  archived: "neutral",
};

const VERIFICATION_TONES: Record<VerificationStatus, ChipTone> = {
  not_started: "neutral",
  submitted: "pending",
  in_review: "pending",
  approved: "success",
  rejected: "danger",
  changes_requested: "warning",
  expired: "warning",
};

const APPLICATION_TONES: Record<ApplicationStatus, ChipTone> = {
  applied: "pending",
  shortlisted: "success",
  interview: "success",
  offered: "success",
  withdrawn: "neutral",
  declined: "neutral",
  rejected: "danger",
  expired: "neutral",
};

export function GigStatusChip({ status }: { status: GigStatus }) {
  return <Chip tone={GIG_TONES[status]}>{GIG_STATUS_LABELS[status]}</Chip>;
}

export function VerificationChip({ status }: { status: VerificationStatus }) {
  return <Chip tone={VERIFICATION_TONES[status]}>{VERIFICATION_STATUS_LABELS[status]}</Chip>;
}

export function ApplicationStatusChip({ status }: { status: ApplicationStatus }) {
  return <Chip tone={APPLICATION_TONES[status]}>{APPLICATION_STATUS_LABELS[status]}</Chip>;
}
