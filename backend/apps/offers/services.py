"""Making, answering and countering offers.

The negotiation for one application:

1. The vendor sends an offer (revision 1). The application becomes offered and the
   talent has 48 hours to answer.
2. The talent accepts (a booking is created and agreement version 1 drawn up from the
   terms), declines (the application is declined), or asks for a change once: a counter
   that may only touch terms.COUNTERABLE.
3. On a counter the vendor accepts it (the booking is made on the countered terms) or
   declines it, which sends the original terms back as a final offer the talent can only
   accept or decline.

Each answer gives the other side a fresh 48 hours. Locks are taken gig first, then the
application, then the offer (the same order as everywhere else).
"""

from django.db import transaction
from django.utils import timezone

from apps.applications import services as applications
from apps.applications.constants import ApplicationStatus
from apps.applications.models import Application
from apps.bookings.lifecycle import OFFER_TTL, Actor
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action, snapshot
from apps.offers import terms as offer_terms
from apps.offers.models import Offer, OfferStatus, Party

AUDIT_FIELDS = ["status", "status_reason"]
# Application events after which no offer can still be open.
ENDING_EVENTS = (
    "application.withdrawn",
    "application.rejected",
    "application.declined",
    "application.expired",
)


class OfferError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def party_of(user, application: Application) -> str | None:
    if application.talent_id == user.pk:
        return Party.TALENT
    if application.gig.vendor_id == user.pk:
        return Party.VENDOR
    return None


def offers_for(application_id):
    return Offer.objects.filter(application_id=application_id).order_by("revision")


def open_offer(application_id) -> Offer | None:
    return Offer.objects.filter(application_id=application_id, status=OfferStatus.OPEN).first()


def _payload(offer: Offer, application: Application, **extra) -> dict:
    return {
        "offer_id": str(offer.pk),
        "application_id": str(application.pk),
        "gig_id": str(application.gig_id),
        "gig_title": application.gig.title,
        "talent_id": str(application.talent_id),
        "vendor_id": str(application.gig.vendor_id),
        "revision": offer.revision,
        **extra,
    }


def _create(application, *, revision, by, user, terms, now, message="", counter_of=None, final):
    offer = Offer.objects.create(
        application=application,
        revision=revision,
        proposed_by=by,
        created_by=user,
        terms=terms,
        terms_sha256=offer_terms.digest(terms),
        counter_of=counter_of,
        final=final,
        message=message.strip(),
        created_at=now,
    )
    log_action(
        actor=user,
        action="offer.sent",
        obj=offer,
        after={
            "revision": revision,
            "by": by,
            "terms_sha256": offer.terms_sha256,
            "stipend_amount": terms["stipend_amount"],
            "final": final,
        },
    )
    return offer


def _answer(offer: Offer, status: str, *, user, reason: str = "", now, request=None) -> None:
    before = snapshot(offer, AUDIT_FIELDS)
    offer.status = status
    offer.status_reason = reason
    offer.answered_at = now
    offer.save(update_fields=["status", "status_reason", "answered_at"])
    log_action(
        actor=user,
        action=f"offer.{status}",
        obj=offer,
        before=before,
        after=snapshot(offer, AUDIT_FIELDS),
        request=request,
    )


def _give_more_time(application: Application, *, user, now, request=None) -> None:
    """The other side's turn: they get a fresh OFFER_TTL to answer."""
    before = snapshot(application, ["offer_expires_at"])
    application.offer_expires_at = now + OFFER_TTL
    application.save(update_fields=["offer_expires_at", "updated_at"])
    log_action(
        actor=user,
        action="application.offer_deadline_moved",
        obj=application,
        before=before,
        after=snapshot(application, ["offer_expires_at"]),
        request=request,
    )


def _lock(offer_id):
    """Lock gig, application, then the offer. Returns (application, offer)."""
    application_id = Offer.objects.values_list("application_id", flat=True).get(pk=offer_id)
    application = applications.lock(application_id)
    offer = Offer.objects.select_for_update().get(pk=offer_id)
    return application, offer


def _open_for(offer: Offer, application: Application, user) -> str:
    """The caller's side, after checking the offer is theirs to answer."""
    party = party_of(user, application)
    if party is None:
        raise Offer.DoesNotExist
    if offer.status != OfferStatus.OPEN:
        raise OfferError(f"This offer is {offer.get_status_display().lower()}.")
    if party != offer.recipient:
        raise OfferError("You sent this one; it's waiting for the other side.", status=403)
    return party


# ---------- The vendor ----------


def make_offer(application_id, *, vendor, terms: dict, message: str = "", request=None, now=None):
    """Send the first offer, with its terms. The application becomes offered."""
    now = now or timezone.now()
    with transaction.atomic():
        application = applications.lock(application_id)
        if application.gig.vendor_id != vendor.pk:
            raise Application.DoesNotExist
        if Offer.objects.filter(application=application).exists():
            raise OfferError("This application already has an offer.")
        frozen = offer_terms.validate(
            terms,
            compensation_model=application.gig.compensation_model,
            today=timezone.localdate(now),
        )
        try:
            applications.move(
                application,
                ApplicationStatus.OFFERED,
                actor=Actor.VENDOR,
                user=vendor,
                reason=message,
                request=request,
                now=now,
            )
        except applications.InvalidApplicationTransition as exc:
            raise OfferError(str(exc)) from exc
        return _create(
            application, revision=1, by=Party.VENDOR, user=vendor, terms=frozen, now=now,
            message=message, final=False,
        )  # fmt: skip


# ---------- Answering ----------


def accept(offer_id, *, user, request=None, now=None):
    """Accept the open offer addressed to you. Books the slot and draws up the agreement.

    The talent accepts the vendor's offer; the vendor accepts the talent's counter.
    """
    from apps.agreements import services as agreements
    from apps.bookings import services as bookings

    now = now or timezone.now()
    with transaction.atomic():
        application, offer = _lock(offer_id)
        party = _open_for(offer, application, user)
        _answer(offer, OfferStatus.ACCEPTED, user=user, now=now, request=request)
        try:
            booking = bookings.confirm(
                application,
                start=offer_terms_date(offer, "start_date"),
                end=offer_terms_date(offer, "end_date"),
                actor=party,
                user=user,
                request=request,
                now=now,
                metadata={"offer_id": str(offer.pk), "revision": offer.revision},
            )
        except bookings.BookingRefused as exc:
            raise OfferError(str(exc)) from exc
        version = agreements.draw_up(booking, offer, user=user, request=request, now=now)
    # Outside the transaction: a slow or failed render doesn't undo the booking; the
    # agreements job retries anything left unrendered.
    agreements.render_quietly(version.pk)
    return booking


def offer_terms_date(offer: Offer, name: str):
    from datetime import date

    return date.fromisoformat(offer.terms[name])


def decline(offer_id, *, user, reason: str = "", request=None, now=None) -> Offer:
    """Say no to the open offer addressed to you.

    The talent declining the vendor's offer declines the application. The vendor
    declining the talent's counter sends the original terms back as a final offer.
    """
    now = now or timezone.now()
    reason = reason.strip()
    with transaction.atomic():
        application, offer = _lock(offer_id)
        party = _open_for(offer, application, user)
        _answer(offer, OfferStatus.DECLINED, user=user, reason=reason, now=now, request=request)
        if party == Party.TALENT:
            try:
                applications.move(
                    application,
                    ApplicationStatus.DECLINED,
                    actor=Actor.TALENT,
                    user=user,
                    reason=reason,
                    request=request,
                    now=now,
                )
            except applications.InvalidApplicationTransition as exc:
                raise OfferError(str(exc)) from exc
            return offer
        original = offer.counter_of
        reissued = _create(
            application, revision=offer.revision + 1, by=Party.VENDOR, user=user,
            terms=original.terms, now=now, message=reason, counter_of=offer, final=True,
        )  # fmt: skip
        _give_more_time(application, user=user, now=now, request=request)
        publish(
            DomainEvent(
                "offer.counter_declined",
                _payload(reissued, application, message=reason),
                occurred_at=now,
            )
        )
        return reissued


def counter(offer_id, *, talent, changes: dict, message: str = "", request=None, now=None):
    """The talent asks for a change: once per application, and only to COUNTERABLE terms."""
    now = now or timezone.now()
    with transaction.atomic():
        application, offer = _lock(offer_id)
        party = _open_for(offer, application, talent)
        if party != Party.TALENT:
            raise OfferError("Only the talent can ask for a change.", status=403)
        if (
            offer.final
            or Offer.objects.filter(application=application, proposed_by=Party.TALENT).exists()
        ):
            raise OfferError("You've already asked for a change once. Accept or decline.")
        not_allowed = sorted(set(changes) - set(offer_terms.COUNTERABLE))
        if not_allowed:
            raise OfferError(
                f"You can't change {', '.join(not_allowed)}. You can change: "
                f"{', '.join(offer_terms.COUNTERABLE)}.",
                status=400,
            )
        proposed = offer_terms.validate(
            {**offer.terms, **changes},
            compensation_model=application.gig.compensation_model,
            today=timezone.localdate(now),
        )
        changed = offer_terms.changed_fields(offer.terms, proposed)
        if not changed:
            raise OfferError("Change at least one of the terms.", status=400)
        _answer(offer, OfferStatus.COUNTERED, user=talent, now=now, request=request)
        countered = _create(
            application, revision=offer.revision + 1, by=Party.TALENT, user=talent,
            terms=proposed, now=now, message=message, counter_of=offer, final=True,
        )  # fmt: skip
        _give_more_time(application, user=talent, now=now, request=request)
        publish(
            DomainEvent(
                "offer.countered",
                _payload(countered, application, changed=changed, message=countered.message),
                occurred_at=now,
            )
        )
        return countered


# ---------- Ending ----------


def lapse_open_offers(event: DomainEvent) -> None:
    """Subscribed to ENDING_EVENTS: an application that ended has no open offer."""
    now = event.occurred_at or timezone.now()
    for offer in Offer.objects.select_for_update().filter(
        application_id=event.payload["application_id"], status=OfferStatus.OPEN
    ):
        _answer(
            offer,
            OfferStatus.LAPSED,
            user=None,
            reason=f"The application was {event.payload['to']}.",
            now=now,
        )
