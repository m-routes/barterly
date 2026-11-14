from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.verification.providers.base import KycOutcome, KycResult
from apps.verification.providers.fake import FakeKycProvider
from apps.verification.services.kyc import handle_webhook


class Command(BaseCommand):
    help = "Local only: deliver a signed fake KYC webhook for a started ID check."

    def add_arguments(self, parser):
        parser.add_argument(
            "reference", help="The session reference from /verification/checks/id/."
        )
        parser.add_argument("outcome", choices=KycOutcome.values)
        parser.add_argument("--reason", default="")
        parser.add_argument("--last-four", default="1234")

    def handle(self, *args, **options):
        if not settings.KYC_PROVIDER.endswith(".FakeKycProvider"):
            raise CommandError("Only works with the fake KYC provider (local development).")
        result = KycResult(
            reference=options["reference"],
            outcome=options["outcome"],
            reason=options["reason"],
            id_last_four=options["last_four"],
        )
        body, headers = FakeKycProvider.webhook_request(result)
        self.stdout.write(f"Webhook outcome: {handle_webhook(headers, body)}")
