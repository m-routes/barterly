from django.utils import timezone

from apps.gigs.constants import GigStatus
from apps.gigs.tests.factories import GigFactory, in_days
from apps.profiles.tests.factories import TalentProfileFactory
from apps.verification.constants import BadgeKind
from apps.verification.models import Badge


def eligible_talent(**profile):
    """A complete talent profile with a verified ID."""
    talent = TalentProfileFactory(languages=["en", "hi"], instagram_followers=3000, **profile).user
    Badge.objects.create(
        user=talent, kind=BadgeKind.ID_VERIFIED, granted_at=timezone.now(), grant_reason="test"
    )
    return talent


def live_gig(**kwargs):
    gig = GigFactory(**{"status": GigStatus.LIVE, **kwargs})
    gig.published_at = timezone.now()
    gig.save(update_fields=["published_at"])
    return gig


def dates(start=32, end=50):
    """Inside the factory gig (starts in 30 days, ends in 60)."""
    return {"proposed_start": in_days(start), "proposed_end": in_days(end)}
