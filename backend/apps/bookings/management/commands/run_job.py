from django.core.management.base import BaseCommand, CommandError

from apps.bookings import jobs


class Command(BaseCommand):
    help = "Run one scheduled job now (the same code Cloud Scheduler triggers)."

    def add_arguments(self, parser):
        parser.add_argument("job", choices=sorted(jobs.JOBS))

    def handle(self, *args, job, **options):
        try:
            run = jobs.run(job, trigger="manual")
        except jobs.JobAlreadyRunning as exc:
            raise CommandError(f"{job} is already running.") from exc
        self.stdout.write(f"{job}: {run.result}")
