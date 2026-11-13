"""Every migration in our apps must reverse cleanly (rule: reversible migrations)."""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

OUR_APPS = ["profiles", "common", "accounts"]


def applied(app_label: str) -> set[str]:
    executor = MigrationExecutor(connection)
    return {name for app, name in executor.loader.applied_migrations if app == app_label}


@pytest.mark.django_db(transaction=True)
def test_our_migrations_reverse_and_reapply():
    # admin's log table points at the user model, so it has to go down first.
    for app in ["admin", *OUR_APPS]:
        call_command("migrate", app, "zero", verbosity=0)
        assert not applied(app), app

    call_command("migrate", verbosity=0)
    for app in OUR_APPS:
        assert applied(app), app


@pytest.mark.django_db
def test_no_missing_migrations():
    call_command("makemigrations", "--check", "--dry-run", verbosity=0)
