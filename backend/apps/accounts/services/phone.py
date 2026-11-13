"""Phone numbers are the login identifier. They are stored in E.164 (e.g. +919876543210)."""

import phonenumbers
from django.core.exceptions import ValidationError

DEFAULT_REGION = "IN"


def normalize_phone(raw: str, region: str = DEFAULT_REGION) -> str:
    """Parse and validate a phone number and return it in E.164.

    Numbers without a country code are read as Indian. Raises ValidationError for
    anything that isn't a valid, dialable number.
    """
    if not raw or not str(raw).strip():
        raise ValidationError("Enter a phone number.", code="required")
    try:
        number = phonenumbers.parse(str(raw), region)
    except phonenumbers.NumberParseException as exc:
        raise ValidationError("Enter a valid phone number.", code="invalid") from exc
    if not phonenumbers.is_valid_number(number):
        raise ValidationError("Enter a valid phone number.", code="invalid")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)
