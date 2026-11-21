"""What holds a review (or reply) for a person to look at before anyone sees it:
words from settings.REVIEW_FLAGGED_WORDS, and contact details (phone numbers, email
addresses, links), which reviews mustn't carry. Reports from readers queue it too."""

import re

from django.conf import settings

PHONE = re.compile(r"(?:\+?91[\s-]*)?(?<!\d)[6-9]\d(?:[\s-]*\d){8}(?!\d)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LINK = re.compile(r"(https?://|www\.)\S+", re.IGNORECASE)


def flags_for(text: str) -> list[str]:
    lowered = text.lower()
    found = []
    for word in settings.REVIEW_FLAGGED_WORDS:
        if re.search(rf"(?<!\w){re.escape(word.lower())}(?!\w)", lowered):
            found.append(f"word:{word.lower()}")
    if PHONE.search(text):
        found.append("contact:phone")
    if EMAIL.search(text):
        found.append("contact:email")
    if LINK.search(text):
        found.append("contact:link")
    return found
