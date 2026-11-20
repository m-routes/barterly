"""Deliverables: the talent hands in work; the host approves it (releasing the escrow)
or asks for changes. With no answer for ESCROW_AUTO_RELEASE_HOURS after the latest
submission, escrow.auto_release() releases it."""

from django.db import transaction
from django.utils import timezone

from apps.bookings.lifecycle import BookingStatus
from apps.bookings.models import Booking
from apps.common.services.audit import log_action
from apps.money import escrow as escrow_service
from apps.money.models import DeliverableSubmission, Escrow, EscrowStatus, SubmissionReview

OPEN_FOR_WORK = frozenset(
    {BookingStatus.CHECKED_IN, BookingStatus.DELIVERING, BookingStatus.COMPLETED}
)


class DeliverableError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def _event(name: str, booking: Booking, submission: DeliverableSubmission, now, notify) -> None:
    from apps.common.events import DomainEvent, publish

    publish(
        DomainEvent(
            name,
            {
                "booking_id": str(booking.pk),
                "submission_id": str(submission.pk),
                "gig_title": booking.gig.title,
                "talent_id": str(booking.talent_id),
                "vendor_id": str(booking.vendor_id),
                "dedup_key": f"{name}:{submission.pk}",
                "notify": notify,
            },
            occurred_at=now,
        )
    )


def submit(
    booking_id, *, talent, note: str = "", links: list[str] | None = None, request=None, now=None
) -> DeliverableSubmission:
    now = now or timezone.now()
    links = [str(link)[:500] for link in (links or [])][:20]
    if not note.strip() and not links:
        raise DeliverableError("Add a note or at least one link.", 400)
    with transaction.atomic():
        booking = (
            Booking.objects.select_for_update(of=("self",))
            .select_related("gig")
            .get(pk=booking_id, talent=talent)
        )
        if booking.status not in OPEN_FOR_WORK:
            raise DeliverableError("Hand in work once you've checked in.")
        if booking.deliverables.exists():
            raise DeliverableError("Hand in each deliverable from its own card in the app.")
        escrow = Escrow.objects.filter(booking=booking).first()
        if escrow and escrow.status != EscrowStatus.HELD:
            raise DeliverableError("The stipend for this stay is already settled.")
        submission = DeliverableSubmission.objects.create(
            booking=booking, note=note.strip(), links=links, submitted_at=now
        )
        log_action(
            actor=talent,
            action="money.deliverables_submitted",
            obj=submission,
            after={"links": len(links)},
            request=request,
        )
        _event("money.deliverables_submitted", booking, submission, now, ["vendor"])
    return submission


def review(
    submission_id, *, vendor, approve: bool, note: str = "", request=None, now=None
) -> tuple[DeliverableSubmission, Escrow | None, str]:
    """Approve (and release the escrow) or ask for changes. Returns the submission, the
    escrow, and why the money wasn't released if it couldn't be just now."""
    now = now or timezone.now()
    if not approve and not note.strip():
        raise DeliverableError("Say what needs to change.", 400)
    with transaction.atomic():
        submission = (
            DeliverableSubmission.objects.select_for_update(of=("self",))
            .select_related("booking__gig")
            .get(pk=submission_id, booking__vendor=vendor)
        )
        latest = DeliverableSubmission.objects.filter(booking_id=submission.booking_id).first()
        if latest.pk != submission.pk:
            raise DeliverableError("A newer submission is waiting: review that one.")
        if submission.review != SubmissionReview.PENDING:
            raise DeliverableError("You've already answered this one.")
        submission.review = SubmissionReview.APPROVED if approve else SubmissionReview.CHANGES
        submission.review_note, submission.reviewed_at = note.strip()[:1000], now
        submission.save(update_fields=["review", "review_note", "reviewed_at"])
        log_action(
            actor=vendor,
            action=f"money.deliverables_{submission.review}",
            obj=submission,
            after={"note": submission.review_note},
            request=request,
        )
        if not approve:
            _event("money.changes_requested", submission.booking, submission, now, ["talent"])
    escrow = Escrow.objects.filter(booking_id=submission.booking_id).first()
    held_back = ""
    if approve and escrow and escrow.status == EscrowStatus.HELD:
        try:
            escrow = escrow_service.release(
                submission.booking_id, by="vendor", actor=vendor, request=request, now=now
            )
        except escrow_service.EscrowError as exc:
            # The approval stands; the auto-release job retries the release.
            held_back = exc.message
    return submission, escrow, held_back
