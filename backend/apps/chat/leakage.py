"""Contact-sharing guard for chat before a booking is confirmed.

scan() finds phone numbers (digits with any spacing, or spelt out in English or Hindi
number words), emails (including "name at gmail dot com"), links, @handles, UPI IDs and
phrases that move the conversation off Barterly (WhatsApp, Telegram, "insta id", ...),
and returns the text with each match replaced by MASK.

Pure: no database, so the rules are tested on their own (tests/test_leakage.py).
"""

import re
from dataclasses import dataclass, field

from django.db import models

MASK = "[hidden]"

# A run of at least this many digits reads as a phone number. Indian mobiles have 10;
# landlines with an STD code 10-11. Prices, dates and counts stay well under.
MIN_PHONE_DIGITS = 8


class Kind(models.TextChoices):
    PHONE = "phone", "phone number"
    EMAIL = "email", "email address"
    URL = "url", "link"
    HANDLE = "handle", "social handle"
    UPI = "upi", "payment ID"
    OFF_PLATFORM = "off_platform", "off-platform contact"


@dataclass(frozen=True)
class Finding:
    kind: str
    start: int
    end: int


@dataclass
class Result:
    text: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def kinds(self) -> list[str]:
        return sorted({f.kind for f in self.findings})

    @property
    def masked(self) -> bool:
        return bool(self.findings)


# ---------- Phone numbers ----------

NUMBER_WORDS = {
    # English
    "zero": 1, "oh": 1, "one": 1, "two": 1, "three": 1, "four": 1, "five": 1, "six": 1,
    "seven": 1, "eight": 1, "nine": 1,
    # Hindi (romanised)
    "shunya": 1, "ek": 1, "do": 1, "teen": 1, "char": 1, "chaar": 1, "paanch": 1,
    "panch": 1, "chhe": 1, "che": 1, "saat": 1, "sat": 1, "aath": 1, "aat": 1, "nau": 1,
}  # fmt: skip
REPEATERS = {"double": 2, "triple": 3}
# Characters that may sit between the digits of one phone number.
BRIDGES = set("-.()+/_*")
TOKENS = re.compile(r"\d+|[A-Za-z]+|\S")
# 15-11-2026, 2026.11.15: a date, not a phone number.
DATE = re.compile(r"^(\d{1,2}\D+\d{1,2}\D+\d{4}|\d{4}\D+\d{1,2}\D+\d{1,2})$")


def _phones(text: str) -> list[Finding]:
    found: list[Finding] = []
    run_start = run_end = None
    digits = 0
    repeat = 1

    def close():
        nonlocal run_start, run_end, digits, repeat
        long_enough = run_start is not None and digits >= MIN_PHONE_DIGITS
        if long_enough and not DATE.match(text[run_start:run_end]):
            start = run_start - 1 if run_start and text[run_start - 1] == "+" else run_start
            found.append(Finding(Kind.PHONE, start, run_end))
        run_start = run_end = None
        digits, repeat = 0, 1

    for match in TOKENS.finditer(text):
        token = match.group().lower()
        if token.isdigit() or token in NUMBER_WORDS:
            count = len(token) if token.isdigit() else NUMBER_WORDS[token]
            digits += count * repeat
            repeat = 1
            if run_start is None:
                run_start = match.start()
            run_end = match.end()
        elif token in REPEATERS:
            repeat = REPEATERS[token]
            if run_start is None:
                run_start = match.start()
        elif token in BRIDGES and run_start is not None:
            continue
        else:
            close()
    close()
    return found


# ---------- Emails, links, handles, UPI ----------

TLDS = r"(?:com|in|co|org|net|io|me|app|link|ly|gl|xyz|info|biz|us|uk|ai)"
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", re.I)
SPELT_EMAIL = re.compile(
    rf"[\w.+-]+\s*(?:\(at\)|\[at\]|\s+at\s+)\s*[\w-]+\s*(?:\(dot\)|\[dot\]|\s+dot\s+|\.)\s*{TLDS}\b",
    re.I,
)
UPI = re.compile(
    r"(?<![\w.])[\w.-]{2,}@(?:ok\w+|ybl|ibl|axl|upi|paytm|apl|yapl|icici|sbi|hdfc\w*)\b", re.I
)
URL = re.compile(
    rf"(?:https?://|www\.)\S+|\b[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.{TLDS}\b(?:/\S*)?", re.I
)
HANDLE = re.compile(r"(?<![\w@.])@[A-Za-z0-9_.]{3,30}")

# ---------- Phrases that take the conversation elsewhere ----------

PHRASES = re.compile(
    r"\bw\s*h?\s*a\s*t+\s*'?\s*s?\s*a\s*p+\b"  # whatsapp, what's app, watsap
    r"|\bwhtsapp\b"
    r"|\btele\s*gram\b"
    r"|\bsnap\s*chat\b|\bsignal\s+app\b"
    r"|\b(?:insta(?:gram)?|ig)\s*(?:id|handle|account|dm|pe)\b"
    r"|\b(?:my|follow\s+me\s+on|dm\s+me\s+on)\s+insta(?:gram)?\b"
    r"|\bcall\s+me\s+(?:on|at)\b"
    r"|\b(?:my|your)\s+(?:number|no\.?|mobile|cell|phone\s*no\.?|contact\s+number)\b"
    r"|\b(?:g\s*pay|phone\s*pe|paytm|upi\s*id)\b",
    re.I,
)


def _matches(kind: str, pattern: re.Pattern, text: str) -> list[Finding]:
    return [Finding(kind, m.start(), m.end()) for m in pattern.finditer(text)]


def find(text: str) -> list[Finding]:
    """Every match, overlapping ones merged (the earlier detector's kind wins)."""
    found = [
        *_matches(Kind.UPI, UPI, text),
        *_matches(Kind.EMAIL, EMAIL, text),
        *_matches(Kind.EMAIL, SPELT_EMAIL, text),
        *_matches(Kind.URL, URL, text),
        *_matches(Kind.HANDLE, HANDLE, text),
        *_phones(text),
        *_matches(Kind.OFF_PLATFORM, PHRASES, text),
    ]
    found.sort(key=lambda f: (f.start, -f.end))
    merged: list[Finding] = []
    for item in found:
        if merged and item.start < merged[-1].end:
            last = merged[-1]
            merged[-1] = Finding(last.kind, last.start, max(last.end, item.end))
        else:
            merged.append(item)
    return merged


def scan(text: str) -> Result:
    findings = find(text)
    if not findings:
        return Result(text)
    parts, cursor = [], 0
    for item in findings:
        parts += [text[cursor : item.start], MASK]
        cursor = item.end
    parts.append(text[cursor:])
    return Result("".join(parts), findings)


def explain(kinds: list[str]) -> str:
    """What the sender is told when something was hidden."""
    labels = [Kind(k).label for k in kinds]
    what = labels[0] if len(labels) == 1 else ", ".join(labels[:-1]) + " and " + labels[-1]
    return (
        f"We hid a {what}. Contact details can be shared once the booking is confirmed; "
        "until then keep the conversation on Barterly so you're both covered."
    )
