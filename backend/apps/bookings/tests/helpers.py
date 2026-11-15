from apps.applications.constants import ApplicationStatus
from apps.applications.services import apply, transition
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.bookings.lifecycle import Actor
from apps.bookings.services import accept_offer


def offered(gig=None, talent=None, **apply_overrides):
    """An application with an offer on it."""
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
    return transition(
        application.pk, ApplicationStatus.OFFERED, actor=Actor.VENDOR, user=gig.vendor
    )


def booked(gig=None, talent=None, **apply_overrides):
    application = offered(gig, talent, **apply_overrides)
    return accept_offer(application.pk, talent=application.talent)
