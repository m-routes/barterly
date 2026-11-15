"""Rejection reasons a vendor picks from. The applicant reads the template text, plus
the vendor's optional message. Codes are stored so reasons can be counted later."""

from django.db import models


class RejectionReason(models.TextChoices):
    NOT_A_FIT = "not_a_fit", "Not the right fit"
    DATES = "dates", "Dates don't work"
    FILLED = "filled", "Already filled"
    LANGUAGE = "language", "Language needed"
    INCOMPLETE = "incomplete", "Missing information"
    OTHER = "other", "Other"
    AUTO_RULE = "auto_rule", "Didn't meet the host's requirements"  # set by auto-reject rules


TEMPLATES: dict[str, str] = {
    RejectionReason.NOT_A_FIT: (
        "The host went with applicants whose skills match this gig more closely."
    ),
    RejectionReason.DATES: "Your dates don't work for this gig.",
    RejectionReason.FILLED: "The host has filled this gig.",
    RejectionReason.LANGUAGE: "This gig needs a language you didn't list.",
    RejectionReason.INCOMPLETE: "Your application was missing information the host needed.",
    RejectionReason.OTHER: "The host decided not to go ahead with your application.",
    RejectionReason.AUTO_RULE: "Your application didn't meet the host's requirements:",
}

# Reasons a vendor may choose (auto_rule is only set by the system).
VENDOR_REASONS = [r for r in RejectionReason.values if r != RejectionReason.AUTO_RULE]
MAX_MESSAGE = 400


def compose(code: str, message: str = "") -> str:
    """What the applicant reads: the template, then the host's own words if any."""
    text = TEMPLATES[code]
    message = message.strip()
    if message:
        separator = " " if code == RejectionReason.AUTO_RULE else " Message from the host: "
        text = f"{text}{separator}{message}"
    return text[:500]
