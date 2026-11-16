from apps.applications.models import Application
from apps.offers import services
from apps.offers.terms import draft_for


def make_offer_for(application, message: str = "", **changes):
    """Offer the gig's terms (with the applicant's dates), changed by `changes`."""
    application = Application.objects.select_related("gig").get(pk=application.pk)
    terms = {**draft_for(application), **changes}
    return services.make_offer(
        application.pk, vendor=application.gig.vendor, terms=terms, message=message
    )
