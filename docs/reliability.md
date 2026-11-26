# Reliability score (v2)

Every person has a reliability score from 0 to 100 on each side they work on: as talent, and as a host. Hosts see an applicant's score as talent; talent see the host's score on an offer. Everyone starts at a neutral **50**.

The formula is one pure function, `apps/reliability/score.py`, with unit tests in `apps/reliability/tests/test_score.py`. `apps/reliability/services.py` counts the events and stores the result.

## The formula

```
score = clamp(50
              + min(6 × completed, 30)
              + min(1 × on-time replies, 10)
              − 10 × late cancellations
              − 20 × last-minute cancellations
              + min(2 × good reviews, 10)
              − 25 × no-shows
              − 8 × poor reviews,
              0, 100)
```

| Term | Points | Limit |
|---|---|---|
| Start | 50 | |
| Each completed booking | +6 | +30 at most (5 bookings) |
| Each on-time reply | +1 | +10 at most |
| Each late cancellation | −10 | none |
| Each last-minute cancellation | −20 | none |
| Each no-show | −25 | none |
| Each good review (4 or 5 stars) | +2 | +10 at most |
| Each poor review (1 or 2 stars) | −8 | none |

The gains are capped and the penalties aren't, so a long record can't buy immunity: someone with many completed stays and one no-show sits at 65, not 100.

**Levels.** "New" until the person has a completed booking, a published review, a counted cancellation or a no-show (replies alone don't end it). After that: excellent (80 and up), good (60 to 79), fair (40 to 59), poor (below 40).

## What counts

| Input | Talent side | Host side |
|---|---|---|
| Completed | Their bookings that reached completed or reviewed | The same, for bookings at their gigs |
| On-time replies | Host offers they accepted, declined or countered before the offer lapsed (48 hours) | Talent counters they accepted or declined in time |
| Late cancellations | Confirmed bookings they cancelled inside the agreement's notice period | The same, cancelled by the host |
| Last-minute cancellations | Confirmed bookings they cancelled a day or less before the stay | The same, cancelled by the host |
| No-shows | Bookings marked no-show (a disputed no-show stops counting while disputed, and for good if the dispute is upheld) | Not tracked |
| Good / poor reviews | Published reviews of them as talent with 4–5 / 1–2 stars (3 stars counts neither way; removed reviews don't count) | The same, as a host |

The notice period comes from the agreement's cancellation policy: flexible 3 days, moderate 7, strict 14. Cancelling before both sides have signed, before the notice period, or by Barterly (an admin, or the system when every place filled) costs nothing. A lapsed offer earns nothing, but isn't penalised in v1.

## When it changes

The stored score is recomputed, inside the same transaction, after each of: `booking.completed`, `booking.reviewed`, `booking.no_show`, `booking.disputed`, `booking.cancelled`, `application.confirmed`, `application.declined`, `offer.countered`, `offer.counter_declined`, `reviews.published` and `reviews.removed`, and nightly by the `reputation_recompute` job. A change of score or level is audited as `reliability.changed`.

## Versions

- **v2** added the review signals (apps.reviews). After deploying it, run
  `python manage.py recompute_reliability` once so stored scores move to v2. The nightly
  job also refreshes everyone with a booking in the last year.
- v1: completion, replies, cancellations and no-shows.

Not yet: decay (an old cancellation counts as much as a new one), and marking hosts as
no-shows. Changing the formula means a new version and a recompute of every stored score.
