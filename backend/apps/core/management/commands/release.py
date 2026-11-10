"""Release tasks run by the Cloud Run migrate job before a revision gets traffic."""

from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Apply migrations and upload static files. Run once per deploy, before traffic moves."

    def add_arguments(self, parser):
        parser.add_argument(
            "--skip-static",
            action="store_true",
            help="Only run migrations.",
        )

    def handle(self, *args, **options):
        self.stdout.write("Applying migrations")
        call_command("migrate", interactive=False, verbosity=options["verbosity"])
        if options["skip_static"]:
            self.stdout.write("Skipping collectstatic")
        else:
            self.stdout.write("Collecting static files")
            call_command("collectstatic", interactive=False, verbosity=options["verbosity"])
        self.stdout.write(self.style.SUCCESS("Release tasks complete"))
