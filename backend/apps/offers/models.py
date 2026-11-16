"""Offers: the terms a vendor sends, and the talent's one counter.

Each offer is one revision of the negotiation for an application, with its terms frozen
(a database trigger refuses changes to terms and terms_sha256, and deletes). Change
offers only through apps.offers.services.
"""

import uuid

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Party(models.TextChoices):
    VENDOR = "vendor", "The host"
    TALENT = "talent", "The talent"


class OfferStatus(models.TextChoices):
    OPEN = "open", "Waiting for an answer"
    HELD = "held", "On hold until a place opens"
    ACCEPTED = "accepted", "Accepted"
    DECLINED = "declined", "Declined"
    COUNTERED = "countered", "Countered"
    LAPSED = "lapsed", "Lapsed"  # expired, or the application ended


class Offer(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    application = models.ForeignKey(
        "applications.Application", on_delete=models.PROTECT, related_name="offers"
    )
    revision = models.PositiveSmallIntegerField(help_text="1 for the first offer, then 2, 3.")
    proposed_by = models.CharField(max_length=10, choices=Party.choices)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+"
    )
    terms = models.JSONField(encoder=DjangoJSONEncoder, help_text="apps.offers.terms, frozen.")
    terms_sha256 = models.CharField(max_length=64)
    counter_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="counters",
        help_text="The offer this one answers (a counter, or the host's reply to it).",
    )
    final = models.BooleanField(
        default=False, help_text="No counter allowed: the one counter has been used."
    )
    message = models.TextField(max_length=1000, blank=True)
    step_in_for = models.ForeignKey(
        "bookings.Booking",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="step_in_offers",
        help_text="Sent automatically when this booking was cancelled and its place freed.",
    )
    status = models.CharField(max_length=10, choices=OfferStatus.choices, default=OfferStatus.OPEN)
    status_reason = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    answered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["application", "revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["application", "revision"], name="offer_one_per_revision"
            ),
            models.UniqueConstraint(
                fields=["application"],
                condition=Q(status="open"),
                name="offer_one_open_per_application",
            ),
            models.CheckConstraint(
                condition=Q(status__in=OfferStatus.values), name="offer_status_valid"
            ),
            models.CheckConstraint(
                condition=Q(proposed_by__in=Party.values), name="offer_party_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"Offer {self.revision} on {self.application_id} ({self.status})"

    @property
    def recipient(self) -> str:
        return Party.TALENT if self.proposed_by == Party.VENDOR else Party.VENDOR
