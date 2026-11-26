"""Field-level encryption for the most sensitive stored values (ASVS 6.1, 6.2).

AES-256-GCM, a fresh 96-bit nonce per value, the field's model and name bound in as
associated data (a ciphertext copied into another column won't decrypt). Stored as

    enc:v1:<key id>:<base64(nonce || ciphertext || tag)>

Keys come from FIELD_ENCRYPTION_KEYS ("id:base64key,id:base64key", the first one
encrypts, every one decrypts), held in Secret Manager. Rotation: put a new key first,
deploy, run `manage.py reencrypt_fields`, then drop the old key. Local and test runs
derive a key from SECRET_KEY.

Reading a value without the prefix returns it as-is: rows written before a field was
encrypted stay readable until `reencrypt_fields` has run (expand), after which the
fallback can go (contract).
"""

import base64
import hashlib
import os
from functools import cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

PREFIX = "enc:v1:"


class DecryptionError(Exception):
    pass


@cache
def _keys() -> tuple[str, dict[str, bytes]]:
    raw = getattr(settings, "FIELD_ENCRYPTION_KEYS", "")
    keys: dict[str, bytes] = {}
    primary = ""
    if raw:
        for item in raw.split(","):
            kid, _, b64 = item.strip().partition(":")
            key = base64.b64decode(b64)
            if not kid or len(key) != 32:
                raise ImproperlyConfigured("FIELD_ENCRYPTION_KEYS: each key is id:32 bytes base64")
            keys[kid] = key
            primary = primary or kid
    else:
        primary = "local"
        keys["local"] = hashlib.sha256(b"field-encryption:" + settings.SECRET_KEY.encode()).digest()
    return primary, keys


def reset_keys() -> None:
    """Forget cached keys (tests that override FIELD_ENCRYPTION_KEYS)."""
    _keys.cache_clear()


def encrypt(plaintext: str, *, context: str) -> str:
    kid, keys = _keys()
    nonce = os.urandom(12)
    sealed = AESGCM(keys[kid]).encrypt(nonce, plaintext.encode(), context.encode())
    return f"{PREFIX}{kid}:{base64.b64encode(nonce + sealed).decode()}"


def is_encrypted(value: str) -> bool:
    return isinstance(value, str) and value.startswith(PREFIX)


def key_id(value: str) -> str | None:
    return value[len(PREFIX) :].split(":", 1)[0] if is_encrypted(value) else None


def decrypt(stored: str, *, context: str) -> str:
    if not is_encrypted(stored):
        return stored  # written before encryption (see module docstring)
    kid, _, b64 = stored[len(PREFIX) :].partition(":")
    key = _keys()[1].get(kid)
    if key is None:
        raise DecryptionError(f"No key {kid!r} in FIELD_ENCRYPTION_KEYS.")
    blob = base64.b64decode(b64)
    try:
        return AESGCM(key).decrypt(blob[:12], blob[12:], context.encode()).decode()
    except Exception as exc:  # cryptography raises InvalidTag
        raise DecryptionError("The value doesn't decrypt with its key.") from exc


class EncryptedTextField(models.TextField):
    """A text column whose value is encrypted at rest; Python code sees plaintext.

    Can't be filtered or searched on (the stored bytes are random). `max_length`
    limits the plaintext (validators, forms, serializers); the column is unbounded.
    """

    description = "Text, encrypted at rest"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.max_length is not None:
            from django.core.validators import MaxLengthValidator

            self.validators.append(MaxLengthValidator(self.max_length))

    @property
    def context(self) -> str:
        return f"{self.model._meta.label_lower}.{self.attname}"

    def from_db_value(self, value, expression, connection):
        if value in (None, ""):
            return value
        return decrypt(value, context=self.context)

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, "") or is_encrypted(value):
            return value
        return encrypt(value, context=self.context)

    def get_lookup(self, lookup_name):
        # Only "is it set?" questions work on ciphertext; anything else would silently
        # match nothing, so it's an error instead.
        if lookup_name == "isnull":
            return super().get_lookup(lookup_name)
        if lookup_name == "exact":
            return _BlankOnlyExact
        return None


class _BlankOnlyExact(models.lookups.Exact):
    def get_prep_lookup(self):
        if self.rhs not in ("", None):
            raise ValueError("Encrypted fields can only be compared with ''.")
        return super().get_prep_lookup()


def encrypted_fields():
    """(model, field) for every EncryptedTextField in the project."""
    from django.apps import apps

    for model in apps.get_models():
        for field in model._meta.concrete_fields:
            if isinstance(field, EncryptedTextField):
                yield model, field


def decrypt_column_in_place(schema_editor, table: str, column: str, context: str) -> None:
    """Migration helper (reverse of encrypting a column): write plaintext back.

    Raw SQL on purpose: the historical model's field would encrypt again on save.
    """
    quote = schema_editor.quote_name
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            f"SELECT id, {quote(column)} FROM {quote(table)} "  # nosec B608  # noqa: S608 - quoted names
            f"WHERE {quote(column)} LIKE %s",
            [PREFIX + "%"],
        )
        for pk, stored in cursor.fetchall():
            cursor.execute(
                f"UPDATE {quote(table)} SET {quote(column)} = %s WHERE id = %s",  # nosec B608  # noqa: S608
                [decrypt(stored, context=context), pk],
            )


def reverse_decrypts(*columns: tuple[str, str, str]):
    """RunPython reverse function for (table, column, context) triples."""

    def reverse(apps, schema_editor):
        for table, column, context in columns:
            decrypt_column_in_place(schema_editor, table, column, context)

    return reverse
