"""The beta's KPIs, worked out from the marketplace's own records.

These need no analytics consent: they are counts over bookings, gigs and reviews the
service keeps anyway, and no person is identifiable in the result. docs/beta/kpis.md
defines each one; the definitions here are the source of truth.

Gig metrics look at gigs first published in the window. The two "within 14 days" ones
only count gigs published at least 14 days ago (mature), so a new gig doesn't drag
them down before it had its chance.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from statistics import median

from django.db.models import Avg, Count, Min, OuterRef, Q, Subquery
from django.utils import timezone

FILL_WINDOW = timedelta(days=14)


@dataclass
class Kpi:
    key: str
    label: str
    value: float | None
    unit: str  # "count", "ratio", "hours", "stars"
    sample: int  # how many gigs/bookings/reviews it's based on
    target: float | None = None
    direction: str = "up"  # "up": higher is better; "down": lower is better
    note: str = ""

    @property
    def status(self) -> str:
        if self.value is None or self.sample == 0:
            return "no_data"
        if self.target is None:
            return "info"
        good = self.value >= self.target if self.direction == "up" else self.value < self.target
        return "ok" if good else "bad"

    def as_dict(self) -> dict:
        return {**asdict(self), "status": self.status}


def bounds(end_day: date, days: int) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    end = timezone.make_aware(datetime.combine(end_day + timedelta(days=1), time.min), tz)
    return end - timedelta(days=days), end


def _ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 4) if whole else None


def gig_metrics(start: datetime, end: datetime, now: datetime) -> list[Kpi]:
    from apps.applications.models import Application
    from apps.bookings.models import Booking
    from apps.gigs.models import Gig

    published = Gig.objects.filter(published_at__gte=start, published_at__lt=end)
    first_app = (
        Application.objects.filter(gig=OuterRef("pk"), applied_at__isnull=False)
        .order_by("applied_at")
        .values("applied_at")[:1]
    )
    gigs = list(
        published.annotate(first_applied=Subquery(first_app)).values(
            "pk", "published_at", "first_applied"
        )
    )
    mature = [g for g in gigs if g["published_at"] <= now - FILL_WINDOW]
    mature_ids = [g["pk"] for g in mature]

    apps_14d = 0
    filled = 0
    if mature_ids:
        by_gig = {g["pk"]: g["published_at"] for g in mature}
        for row in Application.objects.filter(
            gig_id__in=mature_ids, applied_at__isnull=False
        ).values("gig_id", "applied_at"):
            if row["applied_at"] <= by_gig[row["gig_id"]] + FILL_WINDOW:
                apps_14d += 1
        first_booking = (
            Booking.objects.filter(gig_id__in=mature_ids)
            .values("gig_id")
            .annotate(first=Min("created_at"))
        )
        filled = sum(
            1 for row in first_booking if row["first"] <= by_gig[row["gig_id"]] + FILL_WINDOW
        )

    waits = [
        (g["first_applied"] - g["published_at"]).total_seconds() / 3600
        for g in gigs
        if g["first_applied"] is not None
    ]
    no_applicant = sum(1 for g in gigs if g["first_applied"] is None)
    return [
        Kpi(
            "applications_per_gig",
            "Applications per gig (first 14 days)",
            round(apps_14d / len(mature), 2) if mature else None,
            "count",
            len(mature),
            target=8,
        ),
        Kpi(
            "fill_rate_14d",
            "Gigs filled within 14 days",
            _ratio(filled, len(mature)),
            "ratio",
            len(mature),
            target=0.70,
        ),
        Kpi(
            "time_to_first_applicant",
            "Time to first applicant (median)",
            round(median(waits), 1) if waits else None,
            "hours",
            len(waits),
            direction="down",
            note=f"{no_applicant} gig{'' if no_applicant == 1 else 's'} with no applicant yet",
        ),
    ]


def booking_metrics(start: datetime, end: datetime) -> list[Kpi]:
    from apps.bookings.lifecycle import BookingStatus as B
    from apps.bookings.models import Booking, BookingEvent

    first_day, last_day = timezone.localdate(start), timezone.localdate(end - timedelta(seconds=1))
    confirmed = Booking.objects.filter(confirmed_at__isnull=False)

    ended = confirmed.filter(end_date__gte=first_day, end_date__lte=last_day)
    done = ended.filter(status__in=[B.COMPLETED, B.REVIEWED]).count()
    not_done = ended.filter(status__in=[B.NO_SHOW, B.DISPUTED, B.REFUNDED, B.CANCELLED]).count()

    # Stays due to start in the window. A cancellation can only happen before check-in,
    # so a cancelled booking never started and isn't counted.
    started = confirmed.filter(start_date__gte=first_day, start_date__lte=last_day).exclude(
        status=B.CANCELLED
    )
    started_total = started.count()
    no_shows = started.filter(status=B.NO_SHOW).count()

    disputes = BookingEvent.objects.filter(
        to_state=B.DISPUTED, created_at__gte=start, created_at__lt=end
    ).count()
    return [
        Kpi(
            "completion_rate",
            "Stays completed",
            _ratio(done, done + not_done),
            "ratio",
            done + not_done,
            note="Of confirmed stays that ended in the window and are settled.",
        ),
        Kpi(
            "no_show_rate",
            "No-shows",
            _ratio(no_shows, started_total),
            "ratio",
            started_total,
            target=0.05,
            direction="down",
        ),
        Kpi(
            "disputes",
            "Disputes raised",
            float(disputes),
            "count",
            started_total,
            note=(
                f"{round(disputes * 100 / started_total, 1)} per 100 stays started"
                if started_total
                else ""
            ),
        ),
    ]


def review_metrics(start: datetime, end: datetime) -> list[Kpi]:
    from apps.reviews.models import Review, ReviewStatus, Side

    published = Review.objects.filter(
        status=ReviewStatus.PUBLISHED, published_at__gte=start, published_at__lt=end
    )
    overall = published.aggregate(avg=Avg("rating"), n=Count("id"))
    sides = {
        row["subject_side"]: (row["avg"], row["n"])
        for row in published.values("subject_side").annotate(avg=Avg("rating"), n=Count("id"))
    }

    def fmt(side):
        avg, n = sides.get(side, (None, 0))
        return f"{avg:.2f} ({n})" if avg is not None else "\u2013"

    return [
        Kpi(
            "average_rating",
            "Average rating",
            round(overall["avg"], 2) if overall["avg"] is not None else None,
            "stars",
            overall["n"],
            note=f"Hosts {fmt(Side.HOST)} · Talent {fmt(Side.TALENT)}",
        )
    ]


def _active_vendors(start: datetime, end: datetime) -> set:
    from apps.gigs.models import Gig

    return set(
        Gig.objects.filter(published_at__lt=end)
        .filter(Q(closed_at__isnull=True) | Q(closed_at__gte=start))
        .values_list("vendor_id", flat=True)
    )


def vendor_churn(start: datetime, end: datetime) -> Kpi:
    """Hosts with a gig live in the previous window of the same length and none in this one."""
    before = _active_vendors(start - (end - start), start)
    now_active = _active_vendors(start, end)
    churned = len(before - now_active)
    return Kpi(
        "vendor_churn",
        "Host churn",
        _ratio(churned, len(before)),
        "ratio",
        len(before),
        direction="down",
        note=(
            f"{churned} of {len(before)} hosts active the window before had no live gig in this one"
        ),
    )


def compute(end_day: date, days: int, now=None) -> list[Kpi]:
    now = now or timezone.now()
    start, end = bounds(end_day, days)
    return [
        *gig_metrics(start, end, now),
        *booking_metrics(start, end),
        *review_metrics(start, end),
        vendor_churn(start, end),
    ]


def snapshot(now=None, days: int = 28) -> dict:
    """The analytics_kpi_snapshot job: keep yesterday's 28-day KPIs for the trend."""
    from apps.analytics.models import KpiSnapshot

    now = now or timezone.now()
    day = timezone.localdate(now) - timedelta(days=1)
    metrics = {k.key: k.as_dict() for k in compute(day, days, now)}
    KpiSnapshot.objects.update_or_create(
        day=day, window_days=days, defaults={"metrics": metrics, "computed_at": now}
    )
    return {"day": day.isoformat(), "metrics": len(metrics)}
