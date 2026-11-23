"""Encrypt (or re-encrypt with the newest key) every EncryptedTextField value.

Run once after deploying a newly encrypted field (plaintext rows → ciphertext), and
after putting a new key first in FIELD_ENCRYPTION_KEYS (old-key rows → new key).
Idempotent and resumable; rows already under the newest key are skipped. --check
only counts what's left, and exits 1 if anything is.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.common import encryption

BATCH = 500


class Command(BaseCommand):
    help = "Encrypt plaintext rows and move old-key rows to the newest field key."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Count only; change nothing.")

    def handle(self, *args, check: bool = False, **options):
        primary, _ = encryption._keys()
        stale_total = 0
        for model, field in encryption.encrypted_fields():
            table, column = model._meta.db_table, field.column
            quote = connection.ops.quote_name
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT {quote(model._meta.pk.column)}, {quote(column)} "  # nosec B608  # noqa: S608
                    f"FROM {quote(table)} WHERE {quote(column)} <> ''"
                )
                rows = cursor.fetchall()
            stale = [
                (pk, value)
                for pk, value in rows
                if value is not None and encryption.key_id(value) != primary
            ]
            stale_total += len(stale)
            label = f"{model._meta.label}.{field.name}"
            if check:
                self.stdout.write(f"{label}: {len(stale)} of {len(rows)} to (re)encrypt")
                continue
            for start in range(0, len(stale), BATCH):
                with transaction.atomic(), connection.cursor() as cursor:
                    for pk, value in stale[start : start + BATCH]:
                        plain = encryption.decrypt(value, context=field.context)
                        cursor.execute(
                            f"UPDATE {quote(table)} SET {quote(column)} = %s "  # nosec B608  # noqa: S608
                            f"WHERE {quote(model._meta.pk.column)} = %s AND {quote(column)} = %s",
                            [encryption.encrypt(plain, context=field.context), pk, value],
                        )
            self.stdout.write(f"{label}: {len(stale)} row(s) encrypted with key {primary!r}")
        if check and stale_total:
            raise CommandError(f"{stale_total} value(s) not under key {primary!r} yet.")
