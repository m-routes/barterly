import { Chip, type ChipTone } from "@/components/ui/StatusChip";
import type { Reliability } from "@/lib/api/types";

const LEVELS: Record<Reliability["level"], { label: string; tone: ChipTone }> = {
  new: { label: "New", tone: "neutral" },
  excellent: { label: "Excellent", tone: "success" },
  good: { label: "Good", tone: "success" },
  fair: { label: "Fair", tone: "warning" },
  poor: { label: "Poor", tone: "danger" },
};

/** Reliability: a score out of 100 and its level (docs/reliability.md). */
export function ReliabilityBadge({ reliability }: { reliability: Reliability }) {
  const { label, tone } = LEVELS[reliability.level];
  return (
    <Chip tone={tone}>
      Reliability {reliability.score}/100 · {label}
    </Chip>
  );
}
