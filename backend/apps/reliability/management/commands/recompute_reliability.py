"""Recompute every stored reliability score with the current formula. Run once after a
deploy that changes the formula (docs/reliability.md):

    python manage.py recompute_reliability
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.reliability import services
from apps.reliability.models import ReliabilityScore
from apps.reliability.score import VERSION


class Command(BaseCommand):
    help = "Recompute every stored reliability score with the current formula."

    def handle(self, *args, **options):
        rows = list(ReliabilityScore.objects.values_list("user_id", "side"))
        for user_id, side in rows:
            with transaction.atomic():
                services.recompute(user_id, side)
        self.stdout.write(f"Recomputed {len(rows)} score(s) with reliability {VERSION}.")
