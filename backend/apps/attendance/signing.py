"""Signed check-in tokens (Ed25519) and six-digit codes (TOTP).

A token is `BRT1.<payload>.<signature>`, both parts base64url without padding. The
payload is compact JSON: {"v": 1, "kid", "b": booking, "t": talent, "p": pass,
"nbf", "exp"} (times in Unix seconds). The vendor console verifies it offline with the
public key it cached (GET /api/v1/attendance/keys/), so the QR works without signal.

The private key is settings.ATTENDANCE_SIGNING_KEY (32 bytes, base64; Secret Manager in
deployed environments). Rotating it: move the old public key into
ATTENDANCE_PREVIOUS_PUBLIC_KEYS for a day so passes already handed out still verify.

The code is RFC 6238 TOTP: HMAC-SHA1, six digits, a 5-minute step, with the previous
step also accepted.
"""

import base64
import hashlib
import hmac
import json
import secrets
import struct
from dataclasses import dataclass
from datetime import datetime
from functools import cache

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

PREFIX = "BRT1"
CODE_STEP_SECONDS = 300
CODE_DIGITS = 6


class TokenError(Exception):
    pass


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64url(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@dataclass(frozen=True)
class Key:
    kid: str
    public: Ed25519PublicKey
    raw_public: bytes


def _key_of(public: Ed25519PublicKey) -> Key:
    raw = public.public_bytes(Encoding.Raw, PublicFormat.Raw)
    return Key(hashlib.sha256(raw).hexdigest()[:16], public, raw)


@cache
def _private(seed_b64: str, fallback: str) -> Ed25519PrivateKey:
    if seed_b64:
        seed = base64.b64decode(seed_b64)
    elif fallback:
        # Local runs and tests only (deployed settings require the real key).
        seed = hashlib.sha256(b"attendance-dev-key:" + fallback.encode()).digest()
    else:
        raise ImproperlyConfigured("ATTENDANCE_SIGNING_KEY isn't set.")
    if len(seed) != 32:
        raise ImproperlyConfigured("ATTENDANCE_SIGNING_KEY must be 32 bytes, base64.")
    return Ed25519PrivateKey.from_private_bytes(seed)


def private_key() -> Ed25519PrivateKey:
    fallback = "" if settings.ATTENDANCE_SIGNING_KEY else settings.SECRET_KEY
    return _private(settings.ATTENDANCE_SIGNING_KEY, fallback)


def current_key() -> Key:
    return _key_of(private_key().public_key())


def verification_keys() -> list[Key]:
    keys = [current_key()]
    for raw in settings.ATTENDANCE_PREVIOUS_PUBLIC_KEYS:
        keys.append(_key_of(Ed25519PublicKey.from_public_bytes(base64.b64decode(raw))))
    return keys


def public_keys() -> list[dict]:
    return [
        {"kid": k.kid, "alg": "Ed25519", "public_key": b64url(k.raw_public)}
        for k in verification_keys()
    ]


def sign(*, booking_id, talent_id, pass_id, not_before: datetime, expires: datetime) -> str:
    key = current_key()
    payload = json.dumps(
        {
            "v": 1,
            "kid": key.kid,
            "b": str(booking_id),
            "t": str(talent_id),
            "p": str(pass_id),
            "nbf": int(not_before.timestamp()),
            "exp": int(expires.timestamp()),
        },
        separators=(",", ":"),
    ).encode()
    body = f"{PREFIX}.{b64url(payload)}"
    return f"{body}.{b64url(private_key().sign(body.encode()))}"


def verify(token: str) -> dict:
    """The payload of a genuine token (whatever its times; callers check the window)."""
    try:
        prefix, payload_b64, signature_b64 = token.strip().split(".")
        payload = json.loads(unb64url(payload_b64))
        signature = unb64url(signature_b64)
    except (ValueError, TypeError) as exc:
        raise TokenError("That isn't a Barterly check-in code.") from exc
    if prefix != PREFIX or not isinstance(payload, dict) or payload.get("v") != 1:
        raise TokenError("That isn't a Barterly check-in code.")
    key = next((k for k in verification_keys() if k.kid == payload.get("kid")), None)
    if key is None:
        raise TokenError("This pass was signed with a key that's no longer in use.")
    try:
        key.public.verify(signature, f"{prefix}.{payload_b64}".encode())
    except InvalidSignature as exc:
        raise TokenError("This pass has been tampered with.") from exc
    return payload


# ---------- Six-digit codes ----------


def new_code_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret: str, moment: datetime, *, step_offset: int = 0) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    counter = int(moment.timestamp()) // CODE_STEP_SECONDS + step_offset
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**CODE_DIGITS).zfill(CODE_DIGITS)


def code_matches(secret: str, code: str, moment: datetime) -> bool:
    code = "".join(ch for ch in str(code) if ch.isdigit())
    return any(hmac.compare_digest(code_at(secret, moment, step_offset=o), code) for o in (0, -1))
