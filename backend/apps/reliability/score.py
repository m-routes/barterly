"""Reliability score v2: one pure function from counted events to a 0-100 score.

The formula (docs/reliability.md explains it for people):

    score = clamp(50
                  + min(6 * completed, 30)
                  + min(1 * on_time_replies, 10)
                  + min(2 * good_reviews, 10)
                  - 10 * late_cancellations
                  - 20 * last_minute_cancellations
                  - 25 * no_shows
                  - 8 * poor_reviews,
                  0, 100)

Everyone starts at the neutral 50. Completed bookings, replies on time and good
reviews (4 or 5 stars, published) raise it, up to caps so a long history can't buy
immunity; late cancellations, no-shows and poor reviews (1 or 2 stars) lower it,
without a cap. v2 added the review signals.

Levels: "new" until someone has a completed booking, a review or a penalty, then
excellent (80+), good (60+), fair (40+) or poor.

Nothing here touches the database; apps.reliability.services counts the events.
"""

from dataclasses import asdict, dataclass

VERSION = "v2"
NEUTRAL = 50
MIN_SCORE, MAX_SCORE = 0, 100

PER_COMPLETED, COMPLETED_CAP = 6, 30
PER_ON_TIME_REPLY, ON_TIME_REPLY_CAP = 1, 10
PER_LATE_CANCELLATION = 10
PER_LAST_MINUTE_CANCELLATION = 20
PER_NO_SHOW = 25
PER_GOOD_REVIEW, GOOD_REVIEW_CAP = 2, 10
PER_POOR_REVIEW = 8

LEVELS = ((80, "excellent"), (60, "good"), (40, "fair"), (MIN_SCORE, "poor"))
NEW = "new"


@dataclass(frozen=True)
class Inputs:
    """What one person did on one side (talent or host)."""

    completed: int = 0
    on_time_replies: int = 0
    late_cancellations: int = 0
    last_minute_cancellations: int = 0
    no_shows: int = 0
    good_reviews: int = 0
    poor_reviews: int = 0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a whole number of 0 or more, not {value!r}.")


@dataclass(frozen=True)
class Reliability:
    score: int
    level: str
    breakdown: dict[str, int]  # each term's points, so people can see why
    version: str = VERSION


def score(inputs: Inputs) -> Reliability:
    breakdown = {
        "neutral": NEUTRAL,
        "completed": min(PER_COMPLETED * inputs.completed, COMPLETED_CAP),
        "on_time_replies": min(PER_ON_TIME_REPLY * inputs.on_time_replies, ON_TIME_REPLY_CAP),
        "late_cancellations": -PER_LATE_CANCELLATION * inputs.late_cancellations,
        "last_minute_cancellations": (
            -PER_LAST_MINUTE_CANCELLATION * inputs.last_minute_cancellations
        ),
        "no_shows": -PER_NO_SHOW * inputs.no_shows,
        "good_reviews": min(PER_GOOD_REVIEW * inputs.good_reviews, GOOD_REVIEW_CAP),
        "poor_reviews": -PER_POOR_REVIEW * inputs.poor_reviews,
    }
    value = max(MIN_SCORE, min(MAX_SCORE, sum(breakdown.values())))
    return Reliability(score=value, level=level(inputs, value), breakdown=breakdown)


def level(inputs: Inputs, value: int) -> str:
    has_record = (
        inputs.completed
        or inputs.late_cancellations
        or inputs.last_minute_cancellations
        or inputs.no_shows
        or inputs.good_reviews
        or inputs.poor_reviews
    )
    if not has_record:
        return NEW
    return next(name for floor, name in LEVELS if value >= floor)
