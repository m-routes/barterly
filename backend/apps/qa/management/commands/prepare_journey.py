"""Set up the vendor's half of the talent journeys (apps/qa/journeys.py).

manage.py prepare_journey --talent volunteer > journey.json
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.qa.journeys import prepare
from apps.qa.seed import Seeder, SeedRefused, load_personas


class Command(BaseCommand):
    help = "Prepare the gigs, offer and bookings a talent persona's app journey starts from."

    def add_arguments(self, parser):
        parser.add_argument("--talent", required=True, help="A talent key in qa/personas.json.")

    def handle(self, *args, talent: str, **options):
        personas = load_personas()
        if personas.get(talent, {}).get("role") != "talent":
            raise CommandError(f"{talent!r} isn't a talent persona in qa/personas.json.")
        try:
            ids = prepare(talent, Seeder(personas=personas))
        except SeedRefused as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(ids))  # one line, so a job log carries it whole
