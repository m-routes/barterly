"""Scheduled job: find new gigs for each saved search and queue one alert per search."""

from django.db import transaction
from django.utils import timezone

from apps.discovery.filters import DiscoveryQuerySerializer
from apps.discovery.models import SavedSearch, SavedSearchMatch
from apps.discovery.services import (
    eligibility_for,
    filtered,
    score,
    talent_facts,
    talent_profile,
    talent_signals,
)
from apps.notifications.services import queue_notification

ALERT_KIND = "gigs.search_alert"


def parse_params(stored: dict) -> dict:
    serializer = DiscoveryQuerySerializer(data=stored)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def run_alerts(now=None) -> dict[str, int]:
    """New matches are gigs published since the search was last checked that it hasn't
    matched before. Each search with new matches gets one queued notification."""
    now = now or timezone.now()
    counts = {"searches": 0, "matches": 0, "notifications": 0}
    searches = SavedSearch.objects.filter(
        alerts_enabled=True, talent__is_active=True
    ).select_related("talent")
    for search in searches:
        counts["searches"] += 1
        new = _new_matches(search, now)
        with transaction.atomic():
            matches = [
                SavedSearchMatch(
                    saved_search=search,
                    gig=item.gig,
                    score=item.fit.score,
                    breakdown=item.fit.breakdown(),
                )
                for item in new
            ]
            SavedSearchMatch.objects.bulk_create(matches, ignore_conflicts=True)
            if matches:
                best = sorted(new, key=lambda s: -s.fit.score)
                queue_notification(
                    search.talent,
                    ALERT_KIND,
                    {
                        "saved_search_id": str(search.pk),
                        "saved_search_name": search.name,
                        "count": len(matches),
                        "gigs": [
                            {"id": str(s.gig.pk), "title": s.gig.title, "score": s.fit.score}
                            for s in best[:5]
                        ],
                    },
                )
                counts["notifications"] += 1
                counts["matches"] += len(matches)
            SavedSearch.objects.filter(pk=search.pk).update(last_checked_at=now)
    return counts


def _new_matches(search: SavedSearch, now) -> list:
    params = parse_params(search.params)
    profile = talent_profile(search.talent)
    talent = talent_facts(profile, talent_signals(search.talent), params)
    gigs = (
        filtered(params, eligibility_for(profile))
        .filter(published_at__gt=search.last_checked_at, published_at__lte=now)
        .exclude(search_matches__saved_search=search)
        .prefetch_related("skills")
    )
    return [score(gig, talent) for gig in gigs]
