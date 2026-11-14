"""Saved searches and the gigs they have already matched (so alerts never repeat)."""

import uuid

from django.conf import settings
from django.db import models

from apps.common.models import TimeStampedModel

MAX_SAVED_SEARCHES = 10


class SavedSearch(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    talent = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_searches"
    )
    name = models.CharField(max_length=80)
    params = models.JSONField(help_text="Validated discovery filters, as sent to GET /gigs/.")
    alerts_enabled = models.BooleanField(default=True)
    last_checked_at = models.DateTimeField(
        help_text="Gigs published after this are new for the next alert run."
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.name


class SavedSearchMatch(models.Model):
    """A gig this search matched, with the fit breakdown at the time."""

    saved_search = models.ForeignKey(SavedSearch, on_delete=models.CASCADE, related_name="matches")
    gig = models.ForeignKey("gigs.Gig", on_delete=models.CASCADE, related_name="search_matches")
    score = models.PositiveSmallIntegerField()
    breakdown = models.JSONField()
    matched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-score", "-matched_at"]
        constraints = [
            models.UniqueConstraint(fields=["saved_search", "gig"], name="saved_search_match_once")
        ]

    def __str__(self) -> str:
        return f"{self.gig_id} for {self.saved_search_id} ({self.score})"
