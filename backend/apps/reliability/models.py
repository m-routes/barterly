"""Each person's reliability score, one per side (talent, host).

The score is worked out by apps.reliability.score (a pure function) from counted events
and stored here so lists can show it without counting. apps.reliability.services
recomputes it when one of the counted events happens.
"""

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db.models import Q

from apps.reliability.score import NEUTRAL, NEW, VERSION


class Side(models.TextChoices):
    TALENT = "talent", "As talent"
    VENDOR = "vendor", "As a host"


class ReliabilityScore(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reliability_scores"
    )
    side = models.CharField(max_length=10, choices=Side.choices)
    score = models.PositiveSmallIntegerField(default=NEUTRAL)
    level = models.CharField(max_length=12, default=NEW)
    inputs = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    breakdown = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    version = models.CharField(max_length=10, default=VERSION)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "side"], name="reliability_one_per_side"),
            models.CheckConstraint(
                condition=Q(side__in=Side.values), name="reliability_side_valid"
            ),
            models.CheckConstraint(
                condition=Q(score__gte=0, score__lte=100), name="reliability_score_in_range"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} as {self.side}: {self.score} ({self.level})"
