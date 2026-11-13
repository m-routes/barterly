from datetime import timedelta

from django.core.management.base import BaseCommand

from apps.verification.services.kyc import sync_pending


class Command(BaseCommand):
    help = "Ask the KYC provider for ID checks whose webhook never arrived."

    def add_arguments(self, parser):
        parser.add_argument("--older-than-minutes", type=int, default=30)

    def handle(self, *args, **options):
        counts = sync_pending(timedelta(minutes=options["older_than_minutes"]))
        summary = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "nothing pending"
        self.stdout.write(summary)
