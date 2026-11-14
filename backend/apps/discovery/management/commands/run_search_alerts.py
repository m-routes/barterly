from django.core.management.base import BaseCommand

from apps.discovery.alerts import run_alerts


class Command(BaseCommand):
    help = "Find new gigs for saved searches and queue alert notifications. Run hourly."

    def handle(self, *args, **options):
        counts = run_alerts()
        self.stdout.write(
            f"Checked {counts['searches']} search(es): {counts['matches']} new match(es), "
            f"{counts['notifications']} notification(s) queued."
        )
