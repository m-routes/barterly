"""The KPI dashboard in the back office."""

from datetime import timedelta

from django.contrib.auth.decorators import permission_required
from django.db.models import Count
from django.template.response import TemplateResponse
from django.utils import timezone

from apps.analytics import kpis
from apps.analytics.models import AnalyticsEvent, KpiSnapshot
from apps.backoffice.views import _context

WINDOWS = [(7, "7 days"), (28, "28 days"), (90, "90 days")]
TREND_KEYS = [
    "applications_per_gig",
    "fill_rate_14d",
    "time_to_first_applicant",
    "completion_rate",
    "no_show_rate",
    "disputes",
    "average_rating",
    "vendor_churn",
]


def _funnel(start, end) -> list[tuple[str, int, int]]:
    rows = (
        AnalyticsEvent.objects.filter(occurred_at__gte=start, occurred_at__lt=end)
        .values("name")
        .annotate(events=Count("id"), people=Count("actor", distinct=True))
        .order_by("-events")
    )
    return [(r["name"], r["events"], r["people"]) for r in rows]


@permission_required("analytics.view_kpis", raise_exception=True)
def dashboard(request):
    try:
        days = int(request.GET.get("days", 28))
    except ValueError:
        days = 28
    days = days if days in dict(WINDOWS) else 28
    today = timezone.localdate()
    metrics = kpis.compute(today, days)
    start, end = kpis.bounds(today, days)
    trend = list(KpiSnapshot.objects.filter(window_days=28).order_by("-day")[:84:7])
    return TemplateResponse(
        request,
        "analytics/dashboard.html",
        _context(
            request,
            title="Beta KPIs",
            days=days,
            windows=WINDOWS,
            start=start,
            end=end - timedelta(seconds=1),
            metrics=metrics,
            trend=[(s.day, [s.metrics.get(k, {}) for k in TREND_KEYS]) for s in reversed(trend)],
            trend_labels=[next((m.label for m in metrics if m.key == k), k) for k in TREND_KEYS],
            funnel=_funnel(start, end),
        ),
    )
