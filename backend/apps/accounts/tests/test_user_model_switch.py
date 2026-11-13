"""Reproduces the staging/production state (built-in auth.User already migrated) and
checks the one-time switch to accounts.User."""

import pytest
from django.core.management import call_command
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from apps.accounts.services.user_model_switch import (
    LegacyUsersPresent,
    needs_switch,
    switch_to_custom_user,
)


@pytest.fixture
def legacy_database():
    """Database as it is on staging/production: admin + auth.User, no accounts app."""
    for app in ["admin", "profiles", "common", "accounts"]:
        call_command("migrate", app, "zero", verbosity=0)
    with connection.cursor() as cursor:
        cursor.execute("CREATE TABLE auth_user (id serial PRIMARY KEY, username varchar(150))")
        cursor.execute(
            "CREATE TABLE auth_user_groups (id serial PRIMARY KEY,"
            " user_id int REFERENCES auth_user(id))"
        )
        cursor.execute(
            "CREATE TABLE django_admin_log (id serial PRIMARY KEY,"
            " user_id int REFERENCES auth_user(id))"
        )
    recorder = MigrationRecorder(connection)
    for name in ["0001_initial", "0002_logentry_remove_auto_add"]:
        recorder.record_applied("admin", name)
    yield
    # Leave the schema as other tests expect it.
    with connection.cursor() as cursor:
        cursor.execute("DROP TABLE IF EXISTS django_admin_log, auth_user_groups, auth_user CASCADE")
    recorder.migration_qs.filter(app="admin").delete()
    call_command("migrate", verbosity=0)


@pytest.mark.django_db(transaction=True)
def test_switches_empty_legacy_database_and_migrate_then_succeeds(legacy_database):
    assert needs_switch()

    dropped = switch_to_custom_user()

    assert dropped == ["django_admin_log", "auth_user_groups", "auth_user"]
    tables = connection.introspection.table_names()
    assert "auth_user" not in tables
    assert not MigrationRecorder(connection).migration_qs.filter(app="admin").exists()
    call_command("migrate", verbosity=0)  # previously InconsistentMigrationHistory
    assert not needs_switch()
    assert switch_to_custom_user() == []  # idempotent


@pytest.mark.django_db(transaction=True)
def test_refuses_when_legacy_users_exist(legacy_database):
    with connection.cursor() as cursor:
        cursor.execute("INSERT INTO auth_user (username) VALUES ('someone')")

    with pytest.raises(LegacyUsersPresent, match="auth_user has rows"):
        switch_to_custom_user()

    assert "auth_user" in connection.introspection.table_names()
    assert MigrationRecorder(connection).migration_qs.filter(app="admin").exists()
    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM auth_user")


@pytest.mark.django_db
def test_already_switched_database_is_left_alone():
    assert not needs_switch()
    assert switch_to_custom_user() == []
