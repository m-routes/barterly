"""The `send_reminders` job: reminders published as domain events, each at most once.

- offer.expiring: an open offer with EXPIRING_WITHIN or less left, to whoever must answer.
- agreement.sign_reminder: a version still waiting for someone's signature a day after it
  was drawn up, to each side that hasn't signed.
- booking.starts_soon: a confirmed stay starting tomorrow, to both sides.

(Interview reminders are hiring's own `send_interview_reminders` job.) Each event carries
`notify` (who it's for) and `dedup_key`, so running the job again sends nothing new.
"""

from datetime import timedelta

from django.utils import timezone

from apps.common.events import DomainEvent, publish

EXPIRING_WITHIN = timedelta(hours=12)
SIGN_AFTER = timedelta(hours=24)


def offers_expiring(now) -> int:
    from apps.applications.constants import ApplicationStatus
    from apps.offers.models import Offer, OfferStatus

    offers = Offer.objects.select_related("application__gig").filter(
        status=OfferStatus.OPEN,
        application__status=ApplicationStatus.OFFERED,
        application__offer_expires_at__gt=now,
        application__offer_expires_at__lte=now + EXPIRING_WITHIN,
    )
    for offer in offers:
        application = offer.application
        left = application.offer_expires_at - now
        publish(
            DomainEvent(
                "offer.expiring",
                {
                    "offer_id": str(offer.pk),
                    "application_id": str(application.pk),
                    "gig_id": str(application.gig_id),
                    "gig_title": application.gig.title,
                    "talent_id": str(application.talent_id),
                    "vendor_id": str(application.gig.vendor_id),
                    "hours_left": max(1, int(left.total_seconds() // 3600)),
                    "offer_expires_at": application.offer_expires_at,
                    "notify": [offer.recipient],
                    "dedup_key": f"offer.expiring:{offer.pk}",
                },
                occurred_at=now,
            )
        )
    return len(offers)


def agreements_to_sign(now) -> int:
    from apps.agreements.models import AgreementVersion, VersionStatus
    from apps.agreements.services import OPEN_BOOKING

    versions = (
        AgreementVersion.objects.select_related("agreement__booking__gig")
        .prefetch_related("signatures")
        .filter(
            status=VersionStatus.AWAITING,
            created_at__lte=now - SIGN_AFTER,
            agreement__booking__status__in=OPEN_BOOKING,
        )
        .exclude(pdf_sha256="")
    )
    sent = 0
    for version in versions:
        booking = version.agreement.booking
        signed = {s.party for s in version.signatures.all()}
        waiting = [side for side in ("talent", "vendor") if side not in signed]
        if not waiting:
            continue
        publish(
            DomainEvent(
                "agreement.sign_reminder",
                {
                    "agreement_id": str(version.agreement_id),
                    "version_id": str(version.pk),
                    "version": version.number,
                    "booking_id": str(booking.pk),
                    "gig_title": booking.gig.title,
                    "talent_id": str(booking.talent_id),
                    "vendor_id": str(booking.vendor_id),
                    "notify": waiting,
                    "dedup_key": f"agreement.sign_reminder:{version.pk}",
                },
                occurred_at=now,
            )
        )
        sent += 1
    return sent


def stays_starting(now) -> int:
    from apps.bookings.lifecycle import BookingStatus
    from apps.bookings.models import Booking

    tomorrow = timezone.localdate(now) + timedelta(days=1)
    bookings = Booking.objects.select_related("gig").filter(
        status=BookingStatus.CONFIRMED, start_date=tomorrow
    )
    for booking in bookings:
        publish(
            DomainEvent(
                "booking.starts_soon",
                {
                    "booking_id": str(booking.pk),
                    "gig_title": booking.gig.title,
                    "talent_id": str(booking.talent_id),
                    "vendor_id": str(booking.vendor_id),
                    "start_date": booking.start_date,
                    "notify": ["talent", "vendor"],
                    "dedup_key": f"booking.starts_soon:{booking.pk}",
                },
                occurred_at=now,
            )
        )
    return len(bookings)


def send_reminders(now) -> dict[str, int]:
    from django.db import transaction

    with transaction.atomic():
        return {
            "offers_expiring": offers_expiring(now),
            "agreements_to_sign": agreements_to_sign(now),
            "stays_starting": stays_starting(now),
        }
