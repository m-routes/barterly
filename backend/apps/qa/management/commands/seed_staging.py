"""Fill a test environment with realistic data (apps/qa/seed.py says what).

    manage.py seed_staging                 # a new batch
    manage.py seed_staging --reset-journeys   # also start the hire journey's personas
                                              # afresh (a new host to onboard, a free
                                              # talent)

Refuses to run where settings.ALLOW_SEED is off (production).
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.qa.seed import Seeder, SeedRefused


class Command(BaseCommand):
    help = "Seed realistic acceptance-test data (not in production)."

    def add_arguments(self, parser):
        parser.add_argument("--batch", type=int, help="Batch number (default: the next one).")
        parser.add_argument(
            "--reset-journeys",
            action="store_true",
            help="Start the hire journey's personas afresh (run before the acceptance suite).",
        )

    def handle(self, *args, batch=None, reset_journeys=False, **options):
        try:
            seeder = Seeder(batch=batch)
            if reset_journeys:
                from apps.qa.journeys import reset_journey_personas

                reset_journey_personas(seeder.personas, seeder)
            report = seeder.run()
        except SeedRefused as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(report.__dict__, default=str))  # one line: logs
