"""Deliverable tracking for barter and hybrid gigs: one row per unit of each spec item
in the agreement, its submissions (versions), the host's reviews, and post stats."""

import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Kind(models.TextChoices):
    REEL = "reel", "Reel"
    STORY = "story", "Story"
    PHOTO_SET = "photo_set", "Photo set"
    GOOGLE_REVIEW = "google_review", "Google review"
    CUSTOM = "custom", "Custom"


class Platform(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram"
    YOUTUBE = "youtube", "YouTube"
    GOOGLE = "google", "Google"
    OTHER = "other", "Other"


class Status(models.TextChoices):
    PENDING = "pending", "Not submitted yet"
    SUBMITTED = "submitted", "Waiting for the host"
    CHANGES_REQUESTED = "changes_requested", "Changes asked for"
    APPROVED = "approved", "Approved"


MAX_CHANGE_ROUNDS = 2


class Deliverable(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.PROTECT, related_name="deliverables"
    )
    spec_index = models.PositiveSmallIntegerField(help_text="Which item of the agreement.")
    unit = models.PositiveSmallIntegerField(help_text="1..quantity of that item.")
    quantity = models.PositiveSmallIntegerField()
    spec_type = models.CharField(max_length=30, help_text="The agreement's deliverable type.")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    platform = models.CharField(max_length=20, choices=Platform.choices)
    title = models.CharField(max_length=120)
    notes = models.CharField(max_length=300, blank=True)
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    change_rounds = models.PositiveSmallIntegerField(default=0)
    disclosure_required = models.BooleanField(
        help_text="A public post: it must carry the collaboration label (#collab, #ad, ...)."
    )
    submitted_at = models.DateTimeField(null=True, blank=True, help_text="Latest submission.")
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["due_date", "spec_index", "unit"]
        constraints = [
            models.UniqueConstraint(
                fields=["booking", "spec_index", "unit"], name="deliverable_one_per_unit"
            ),
            models.CheckConstraint(
                condition=Q(change_rounds__lte=MAX_CHANGE_ROUNDS),
                name="deliverable_change_rounds_capped",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.status})"


class Submission(models.Model):
    """One version of a deliverable: a post link and/or files, and the label check."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    deliverable = models.ForeignKey(
        Deliverable, on_delete=models.PROTECT, related_name="submissions"
    )
    version = models.PositiveSmallIntegerField()
    post_url = models.URLField(max_length=500, blank=True)
    files = models.ManyToManyField("media.MediaFile", blank=True, related_name="+")
    note = models.CharField(max_length=500, blank=True)
    disclosure_confirmed = models.BooleanField(
        default=False, help_text="The talent confirms the post carries the collaboration label."
    )
    disclosure_detected = models.BooleanField(
        null=True, blank=True, help_text="Seen in the post's caption (empty: couldn't check)."
    )
    submitted_at = models.DateTimeField(default=timezone.now)
    review = models.CharField(
        max_length=20,
        choices=[("", "Waiting"), ("approved", "Approved"), ("changes", "Changes asked for")],
        blank=True,
        default="",
    )
    review_note = models.CharField(max_length=1000, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["deliverable", "version"], name="submission_version"),
        ]

    def __str__(self) -> str:
        return f"v{self.version} of {self.deliverable_id}"


class StatsSource(models.TextChoices):
    INSTAGRAM = "instagram", "Instagram API"
    YOUTUBE = "youtube", "YouTube API"
    MANUAL = "manual", "Self-reported"


class PostStats(models.Model):
    """A snapshot of a post's numbers. Manual ones are self-reported, with a screenshot."""

    id = models.BigAutoField(primary_key=True)
    deliverable = models.ForeignKey(Deliverable, on_delete=models.PROTECT, related_name="stats")
    source = models.CharField(max_length=10, choices=StatsSource.choices)
    views = models.BigIntegerField(null=True, blank=True)
    likes = models.BigIntegerField(null=True, blank=True)
    comments = models.BigIntegerField(null=True, blank=True)
    screenshot = models.ForeignKey(
        "media.MediaFile", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    captured_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-captured_at"]
        constraints = [
            models.CheckConstraint(
                condition=~Q(source="manual") | Q(screenshot__isnull=False),
                name="post_stats_manual_has_screenshot",
            ),
            models.CheckConstraint(
                condition=Q(views__gte=0) | Q(views__isnull=True), name="post_stats_views_ok"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.source} stats for {self.deliverable_id}"

    @property
    def self_reported(self) -> bool:
        return self.source == StatsSource.MANUAL
