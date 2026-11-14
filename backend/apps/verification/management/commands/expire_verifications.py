from django.core.management.base import BaseCommand

from apps.verification.services.cases import expire_due_cases


class Command(BaseCommand):
    help = "Expire approved verifications past their expiry date and remove their badges."

    def handle(self, *args, **options):
        count = expire_due_cases()
        self.stdout.write(f"Expired {count} verification(s).")
