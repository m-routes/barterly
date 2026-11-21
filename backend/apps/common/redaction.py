"""PII and secret redaction for logs and error reports (ASVS 7.1.1, 8.3.5).

Two layers, both applied to log records (apps.common.logging) and Sentry events
(config.sentry):

- by key: any mapping key that names something sensitive has its value replaced,
  whatever the value is (so a nested dict of contact details goes too);
- by pattern: strings anywhere are scanned for phone numbers, emails and UPI ids,
  Aadhaar and PAN numbers, bank account numbers, JWTs and bearer tokens.

It is a safety net, not a licence to log PII: code should log ids, not values.
"""

import re
from collections.abc import Mapping

MASK = "[redacted]"

SENSITIVE_KEY = re.compile(
    r"pass(word)?|secret|token|authori[sz]ation|cookie|session|api[_-]?key|otp|signature"
    r"|phone|mobile|email|e_?mail|aadhaa?r|\bpan\b|pan_number|account_number|acct|ifsc|upi"
    r"|vpa|emergency|contact_(name|phone)|address|street|pincode|postcode|latitude|longitude"
    r"|\blat\b|\blng\b|\blon\b|date_of_birth|\bdob\b|provider_ref|fund_account|payout_ref",
    re.IGNORECASE,
)
# Keys that look sensitive by name but only ever hold safe values.
SAFE_KEYS = {"csrf_cookie_used", "token_type", "session_id_present"}

_PATTERNS = [
    # JWTs (Firebase ID tokens, our access tokens).
    re.compile(r"\beyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"),
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    # Emails and UPI ids (name@bank).
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9.-]+)?"),
    # PAN: five letters, four digits, a letter.
    re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b"),
    # Indian mobiles: +91 / 0 prefix optional, 10 digits starting 6-9, spaces allowed.
    re.compile(r"(?<![\d.])(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}(?!\d)"),
    # Aadhaar (12 digits, often grouped 4-4-4) and bank account numbers (9-18 digits).
    re.compile(r"(?<![\d.])\d{4}[\s-]\d{4}[\s-]\d{4}(?!\d)"),
    re.compile(r"(?<![\d.\-])\d{9,18}(?![\d.])"),
]


def redact_text(text: str) -> str:
    for pattern in _PATTERNS:
        text = pattern.sub(MASK, text)
    return text


def is_sensitive_key(key) -> bool:
    return isinstance(key, str) and key not in SAFE_KEYS and bool(SENSITIVE_KEY.search(key))


def redact(value, *, depth: int = 0):
    """A copy of value with sensitive keys masked and PII patterns removed from strings."""
    if depth > 12:
        return MASK
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        return {
            k: (MASK if is_sensitive_key(k) and v not in (None, "") else redact(v, depth=depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(redact(v, depth=depth + 1) for v in value)
    return value
