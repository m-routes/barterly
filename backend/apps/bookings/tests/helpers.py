from apps.applications.services import apply
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.bookings.services import accept_offer
from apps.offers.tests.helpers import make_offer_for


def offered(gig=None, talent=None, **apply_overrides):
    """An application with an offer on it (the gig's terms, the applicant's dates)."""
    gig = gig or live_gig()
    talent = talent or eligible_talent()
    application = apply(
        talent,
        gig.pk,
        pitch="Three seasons at hostels.",
        answers=[],
        attachments=[],
        **{**dates(), **apply_overrides},
    )
    make_offer_for(application)
    application.refresh_from_db()
    return application


def accepted(gig=None, talent=None, **apply_overrides):
    """An accepted offer: the booking is awaiting both signatures."""
    application = offered(gig, talent, **apply_overrides)
    return accept_offer(application.pk, talent=application.talent)


def booked(gig=None, talent=None, **apply_overrides):
    """A confirmed booking: the offer accepted and the agreement signed by both."""
    from apps.agreements.tests.helpers import sign_both

    booking = accepted(gig, talent, **apply_overrides)
    sign_both(booking)
    booking.refresh_from_db()
    return booking
