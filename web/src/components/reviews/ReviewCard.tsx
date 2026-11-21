import type { StayReview } from "@/lib/api/types";
import { formatDate } from "@/lib/format";

export function Stars({ value, label }: { value: number; label?: string }) {
  return (
    <span aria-label={`${label ? `${label}: ` : ""}${value} out of 5`}>
      {"★".repeat(value)}
      <span aria-hidden="true" className="stars__empty">
        {"★".repeat(5 - value)}
      </span>
    </span>
  );
}

/** One published (or your own) review, its category scores and the reply. */
export function ReviewCard({
  review,
  heading,
  actions,
}: {
  review: StayReview;
  heading: string;
  actions?: React.ReactNode;
}) {
  return (
    <article className="review-card stack-sm" aria-label={heading}>
      <header>
        <p className="card-list__title">{heading}</p>
        <p className="card-list__meta">
          <Stars value={review.rating} /> · {review.author_name}
          {review.published_at ? ` · ${formatDate(review.published_at)}` : " · not published yet"}
        </p>
      </header>
      <dl className="review-card__scores">
        {review.categories.map((c) => (
          <div key={c.key}>
            <dt>{c.label}</dt>
            <dd>
              <Stars value={c.score} label={c.label} />
            </dd>
          </div>
        ))}
      </dl>
      <p>{review.text}</p>
      {review.reply ? (
        <blockquote className="review-card__reply">
          <p className="field__hint">Reply</p>
          <p>{review.reply.text}</p>
        </blockquote>
      ) : null}
      {actions}
    </article>
  );
}
