"""Reviews after a completed booking (double-blind), replies, reports, and each
person's reputation."""

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

STARS = [MinValueValidator(1), MaxValueValidator(5)]


class Side(models.TextChoices):
    """Who is being reviewed."""

    TALENT = "talent", "Talent"
    HOST = "host", "Host"


class ReviewStatus(models.TextChoices):
    SUBMITTED = "submitted", "Waiting for the other review"
    HELD = "held", "Held for moderation"
    PUBLISHED = "published", "Published"
    REMOVED = "removed", "Removed by Barterly"


class Review(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    booking = models.ForeignKey(
        "bookings.Booking", on_delete=models.PROTECT, related_name="reviews"
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews_written"
    )
    subject = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reviews_received"
    )
    subject_side = models.CharField(max_length=10, choices=Side.choices)
    rating = models.PositiveSmallIntegerField(validators=STARS)
    communication = models.PositiveSmallIntegerField(validators=STARS)
    accuracy = models.PositiveSmallIntegerField(
        validators=STARS, help_text="Host: accuracy of the listing. Talent: quality of the work."
    )
    safety = models.PositiveSmallIntegerField(validators=STARS)
    reliability = models.PositiveSmallIntegerField(
        validators=STARS, help_text="Host: payment as agreed. Talent: punctuality."
    )
    text = models.TextField(max_length=2000)
    status = models.CharField(
        max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.SUBMITTED
    )
    # Moderation: why it was held (flagged words, contact details) or reported.
    flags = models.JSONField(default=list, blank=True)
    held_until_cleared = models.BooleanField(
        default=False, help_text="Held for moderation before publishing."
    )
    moderated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    moderated_at = models.DateTimeField(null=True, blank=True)
    moderation_note = models.CharField(max_length=300, blank=True)
    submitted_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        ordering = ["-published_at", "-submitted_at"]
        constraints = [
            models.UniqueConstraint(fields=["booking", "author"], name="review_one_per_side"),
            models.CheckConstraint(
                condition=~Q(author=models.F("subject")), name="review_not_of_yourself"
            ),
            *[
                models.CheckConstraint(
                    condition=Q(**{f"{f}__gte": 1, f"{f}__lte": 5}), name=f"review_{f}_1_to_5"
                )
                for f in ("rating", "communication", "accuracy", "safety", "reliability")
            ],
        ]
        permissions = [("moderate_review", "Can allow or remove held and reported reviews")]

    def __str__(self) -> str:
        return f"{self.rating}★ of {self.subject_id} ({self.status})"

    @property
    def is_public(self) -> bool:
        return self.status == ReviewStatus.PUBLISHED


class Reply(models.Model):
    """The reviewed person's one answer, published with (or after) the review."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    review = models.OneToOneField(Review, on_delete=models.PROTECT, related_name="reply")
    text = models.TextField(max_length=1000)
    flags = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=10, choices=ReviewStatus.choices, default=ReviewStatus.PUBLISHED
    )
    created_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return f"Reply to {self.review_id}"


class ReportReason(models.TextChoices):
    ABUSIVE = "abusive", "Abusive or hateful"
    FALSE = "false", "Not true / about something else"
    PRIVATE = "private", "Shares private information"
    SPAM = "spam", "Spam or advertising"
    OTHER = "other", "Something else"


class ReviewReport(models.Model):
    id = models.BigAutoField(primary_key=True)
    review = models.ForeignKey(Review, on_delete=models.PROTECT, related_name="reports")
    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    reason = models.CharField(max_length=10, choices=ReportReason.choices)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["review", "reporter"], name="report_once_each")
        ]

    def __str__(self) -> str:
        return f"{self.reason} report of {self.review_id}"


class Reputation(models.Model):
    """One person's standing on one side, recomputed from reviews and bookings."""

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reputations"
    )
    side = models.CharField(max_length=10, choices=Side.choices)
    rating_average = models.DecimalField(max_digits=3, decimal_places=2, null=True, blank=True)
    review_count = models.PositiveIntegerField(default=0)
    completion_rate = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Percent of ended bookings they completed."
    )
    response_minutes = models.PositiveIntegerField(
        null=True, blank=True, help_text="Median chat reply time, last 90 days."
    )
    badges = models.JSONField(default=list, blank=True)
    metrics = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "side"], name="reputation_one_per_side")
        ]

    def __str__(self) -> str:
        return f"{self.user_id} as {self.side}"
