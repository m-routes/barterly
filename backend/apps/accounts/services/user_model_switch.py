"""One-time switch of an existing database from auth.User to accounts.User.

Staging and production were first migrated with Django's built-in user model. Their
`admin` migrations (django_admin_log -> auth_user) are recorded as applied, so with
AUTH_USER_MODEL = "accounts.User" Django refuses to migrate:

    InconsistentMigrationHistory: Migration admin.0001_initial is applied before its
    dependency accounts.0001_initial

Those databases never had users, so the fix is to drop the empty legacy user and
admin-log tables and forget admin's migrations; `migrate` then recreates them against
accounts.User. This runs automatically from `manage.py release` and only acts when:

- admin is migrated, accounts is not, and the legacy auth_user table exists; and
- auth_user and django_admin_log are both empty (it refuses otherwise: real data needs
  a proper data migration, not this).

auth's Group and Permission tables are kept; they don't reference the user model.
Safe to delete this module once every environment has been switched.
"""

from django.db import connection as default_connection
from django.db import transaction
from django.db.migrations.recorder import MigrationRecorder

LEGACY_TABLES = ["django_admin_log", "auth_user_groups", "auth_user_user_permissions", "auth_user"]
_MUST_BE_EMPTY = ["auth_user", "django_admin_log"]


class LegacyUsersPresent(RuntimeError):
    """The legacy tables contain rows; switching would destroy data."""


def needs_switch(connection=default_connection) -> bool:
    applied = MigrationRecorder(connection).applied_migrations()
    return (
        ("admin", "0001_initial") in applied
        and ("accounts", "0001_initial") not in applied
        and "auth_user" in connection.introspection.table_names()
    )


def switch_to_custom_user(connection=default_connection) -> list[str]:
    """Drop the empty legacy tables and admin's migration records. Returns dropped tables."""
    if not needs_switch(connection):
        return []
    existing = set(connection.introspection.table_names())
    quote = connection.ops.quote_name
    with transaction.atomic(using=connection.alias), connection.cursor() as cursor:
        for table in _MUST_BE_EMPTY:
            if table in existing:
                cursor.execute(f"SELECT EXISTS (SELECT 1 FROM {quote(table)})")  # noqa: S608
                if cursor.fetchone()[0]:
                    raise LegacyUsersPresent(
                        f"{table} has rows; refusing to drop it. Migrate the data instead."
                    )
        dropped = [t for t in LEGACY_TABLES if t in existing]
        for table in dropped:
            cursor.execute(f"DROP TABLE {quote(table)} CASCADE")
        MigrationRecorder(connection).migration_qs.filter(app="admin").delete()
    return dropped
