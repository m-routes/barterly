"""Application statuses. Who may move between them, and when, is in the one transition
table: apps.bookings.lifecycle.TRANSITIONS."""

from django.db import models

MAX_ATTACHMENTS = 8


class ApplicationStatus(models.TextChoices):
    APPLIED = "applied", "Applied"
    WITHDRAWN = "withdrawn", "Withdrawn"
    SHORTLISTED = "shortlisted", "Shortlisted"
    INTERVIEW = "interview", "Interview"
    OFFERED = "offered", "Offered"
    DECLINED = "declined", "Declined"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    CONFIRMED = "confirmed", "Confirmed"  # the talent accepted the offer: see its Booking


A = ApplicationStatus
# An application is "active" in these: one active application per talent per gig.
ACTIVE = frozenset({A.APPLIED, A.SHORTLISTED, A.INTERVIEW, A.OFFERED})
