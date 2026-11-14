"""Application statuses and who may move between them.

The full table is defined now; this phase only uses apply and withdraw. Shortlisting,
interviews, offers and expiry are driven from Phase 3 through the same table.
"""

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


A = ApplicationStatus
# An application is "active" in these: one active application per talent per gig.
ACTIVE = frozenset({A.APPLIED, A.SHORTLISTED, A.INTERVIEW, A.OFFERED})


class Actor(models.TextChoices):
    TALENT = "talent", "The applicant"
    VENDOR = "vendor", "The gig's vendor"
    SYSTEM = "system", "Scheduled job or another service"


T, V, SYS = Actor.TALENT, Actor.VENDOR, Actor.SYSTEM
TRANSITIONS: dict[tuple[str, str], frozenset[str]] = {
    (A.APPLIED, A.SHORTLISTED): frozenset({V}),
    (A.APPLIED, A.INTERVIEW): frozenset({V}),
    (A.APPLIED, A.OFFERED): frozenset({V}),
    (A.SHORTLISTED, A.INTERVIEW): frozenset({V}),
    (A.SHORTLISTED, A.OFFERED): frozenset({V}),
    (A.INTERVIEW, A.OFFERED): frozenset({V}),
    (A.OFFERED, A.DECLINED): frozenset({T}),  # the talent turns the offer down
    # Withdraw: any time until an offer is accepted (acceptance becomes a booking).
    **{(s, A.WITHDRAWN): frozenset({T}) for s in ACTIVE},
    **{(s, A.REJECTED): frozenset({V}) for s in ACTIVE},
    # The gig closed or filled, or an offer went unanswered.
    **{(s, A.EXPIRED): frozenset({SYS}) for s in ACTIVE},
}
