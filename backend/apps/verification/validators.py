"""Number formats, masking and map checks used by the verification checks."""

import math
import re

from django.core.exceptions import ValidationError

# 5 letters, 4 digits, 1 letter; the 4th letter is the holder type (P = person, C = company...).
PAN_RE = re.compile(r"^[A-Z]{3}[ABCFGHJLPT][A-Z][0-9]{4}[A-Z]$")
# 2-digit state code, the holder's PAN, entity number, 'Z', checksum character.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")

# Roughly India's bounding box; a pin outside it is a typo.
INDIA_LAT = (6.0, 37.6)
INDIA_LNG = (68.0, 97.5)


def normalize_pan(value: str) -> str:
    pan = (value or "").strip().upper()
    if not PAN_RE.match(pan):
        raise ValidationError(
            "Enter a valid 10-character PAN, e.g. ABCPE1234F.", code="invalid_pan"
        )
    return pan


def normalize_gstin(value: str) -> str:
    gstin = (value or "").strip().upper()
    if not GSTIN_RE.match(gstin):
        raise ValidationError("Enter a valid 15-character GSTIN.", code="invalid_gstin")
    return gstin


def gstin_matches_pan(gstin: str, pan: str) -> bool:
    """A GSTIN embeds its holder's PAN in characters 3 to 12."""
    return gstin[2:12] == pan


def last_four(value: str) -> str:
    """The only part of a number we keep."""
    return (value or "").strip()[-4:]


def mask(last4: str, length: int) -> str:
    """Display form, e.g. mask('234F', 10) -> 'XXXXXX234F'."""
    return "X" * max(length - len(last4), 0) + last4 if last4 else ""


def validate_in_india(latitude: float, longitude: float) -> None:
    if not (INDIA_LAT[0] <= latitude <= INDIA_LAT[1] and INDIA_LNG[0] <= longitude <= INDIA_LNG[1]):
        raise ValidationError("That location isn't in India.", code="outside_india")


def distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres (haversine)."""
    radius = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))
