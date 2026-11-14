from django.core.management.base import BaseCommand

from apps.gigs.services import close_expired_gigs


class Command(BaseCommand):
    help = "Close live and paused gigs whose apply-by date has passed. Run daily."

    def handle(self, *args, **options):
        self.stdout.write(f"Closed {close_expired_gigs()} gig(s).")
