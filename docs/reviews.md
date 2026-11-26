# Reviews and reputation

`apps/reviews` (backend); the review panel on Console → Agreements and reputation on
applicant profiles (web); the trip's **Review your host** screen and Profile →
**Reviews and reputation** (mobile).

## Writing a review

- **When:** only for completed stays (booking `completed` or `reviewed`), within
  `REVIEW_WINDOW_DAYS` (14) of completion.
- **Who:** one review per side. The talent reviews the host, and the host reviews the
  talent.
- **What:** an overall rating of 1 to 5 stars, and four category scores of 1 to 5. Their
  labels depend on who's being reviewed:

| Field | Reviewing a host | Reviewing talent |
|---|---|---|
| `communication` | Communication | Communication |
| `accuracy` | Accuracy of the listing | Quality of the work |
| `safety` | Safety | Safety |
| `reliability` | Payment as agreed | Punctuality |

- **Text:** at least `REVIEW_MIN_LENGTH` (20) characters, at most 2,000.

The database enforces one review per side, star ranges and no reviewing yourself.

## Double-blind publishing

- Both reviews stay hidden until both are in, then publish **together**. When that
  happens the booking moves to `reviewed`; the system may now make that move.
- The other side learns they've been reviewed (`reviews.awaiting_yours`), but not what
  was said.
- When the window closes, the hourly `reviews_close_windows` job publishes whatever was
  submitted. Two days before, it reminds whoever hasn't reviewed yet.
- `GET /bookings/<id>/reviews/` shows each side their own review, and the other's only
  once it's published.

## Moderation

A review or reply is **held** for a moderator when it contains:
- a word from `REVIEW_FLAGGED_WORDS`: accusations worth checking, or attempts to move
  off the platform;
- a phone number, an email address or a link.

A held review delays its pair, so the two still publish together.

Anyone signed in can **report** a published review, once each. It then joins the queue,
and stays visible until a moderator decides.

The Trust and Safety role moderates:
- with `GET /admin/reviews/queue/` and `POST /admin/reviews/<id>/moderate/`
  (`allow` or `remove`, with a note);
- or with the actions in the Django admin.

Allowing a held review lets it publish as usual. Removing a review hides it for good and
it stops counting. Every decision is audited.

## Final once published

A published review can't be edited. The service has no edit path, and a database
trigger (migration `reviews.0002`) refuses any change to its stars, text, people or
publication time. Moderation may still change its status. Reviews are never deleted.

The reviewed person can **reply once** (`POST /reviews/<id>/reply/`). A reply can't be
edited either, and it is held too if it carries flagged words or contact details.

## Reputation

`Reputation` holds one row per person and side, recomputed on booking and review events
and nightly (`reputation_recompute`). `GET /users/<id>/reputation/` returns both sides,
and hosts see the talent side on every applicant.

- **Rating:** the average of published reviews, and how many there are.
- **Completion rate:** completed ÷ (completed + no-shows + late or last-minute
  cancellations by them), as a percentage.
- **Response time:** the median minutes they took to answer chat messages over the last
  90 days. A run of messages counts from its first.
- **Badges:** from `REPUTATION_BADGES` in settings.

### Badge rules

Each rule has a key, a label, a side (`talent`, `host` or `any`) and conditions, all of
which must hold. A condition is a metric with a `min` and/or `max`. A metric with no
value yet (a rating before any review) fails.

`apps.reviews.badges.check_rules()` runs at startup. An unknown metric, a duplicate key
or a malformed condition stops the app rather than quietly awarding nothing. Tests cover
both the validation and each shipped badge.

| Badge | Side | Rule |
|---|---|---|
| Verified Creator | talent | ID verified, Instagram linked, at least 1 barter or hybrid gig completed, rating ≥ 4.0 |
| Top Volunteer | talent | at least 3 volunteer gigs completed, rating ≥ 4.5, no no-shows |
| Trusted member | any | at least `TRUSTED_MEMBER_CLEAN_GIGS` (5) clean gigs, no no-shows, no late cancellations |

A **clean gig** is a completed booking that was never disputed, didn't earn them a review
under 4 stars, and where no review they wrote was removed.

Metrics available to rules: `review_count`, `rating_average`, `completed`,
`completed_volunteer_gigs`, `completed_content_gigs`, `clean_gigs`, `no_shows`,
`late_cancellations`, `disputes`, `completion_rate`, `id_verified`, `instagram_linked`.

## Reliability

Published reviews feed reliability **v2** ([reliability.md](reliability.md)). Good reviews
(4–5 stars) add 2 points each, up to 10. Poor reviews (1–2 stars) take 8 each. These
join the completion and no-show signals. After deploying, run
`python manage.py recompute_reliability` once.
