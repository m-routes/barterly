import { Chip } from "@/components/ui/StatusChip";
import type { Reputation } from "@/lib/api/types";

function responseTime(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  return hours < 48 ? `${hours} h` : `${Math.round(hours / 24)} days`;
}

/** Rating, completion rate, response time and badges, as others see them. */
export function ReputationSummary({ reputation }: { reputation: Reputation }) {
  const r = reputation;
  return (
    <div className="stack-sm" aria-label="Reputation">
      <p>
        {r.rating_average ? (
          <>
            <strong>★ {Number(r.rating_average).toFixed(1)}</strong> from {r.review_count} review
            {r.review_count === 1 ? "" : "s"}
          </>
        ) : (
          "No reviews yet"
        )}
        {r.completion_rate !== null ? ` · ${r.completion_rate}% of stays completed` : ""}
        {r.response_minutes !== null
          ? ` · replies in about ${responseTime(r.response_minutes)}`
          : ""}
      </p>
      {r.badges.length ? (
        <div className="chip-row">
          {r.badges.map((b) => (
            <Chip key={b.key} tone="success">
              {b.label}
            </Chip>
          ))}
        </div>
      ) : null}
    </div>
  );
}
