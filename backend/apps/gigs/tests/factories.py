import datetime

import factory
from django.utils import timezone

from apps.gigs.constants import CompensationModel, GigStatus, Meals, RoleTemplate, StayType
from apps.gigs.models import Gig
from apps.properties.tests.factories import PropertyFactory


def in_days(n: int) -> datetime.date:
    return timezone.localdate() + datetime.timedelta(days=n)


class GigFactory(factory.django.DjangoModelFactory):
    """A complete volunteer gig that passes every rule."""

    class Meta:
        model = Gig

    property = factory.SubFactory(PropertyFactory)
    vendor = factory.LazyAttribute(lambda gig: gig.property.vendor)
    title = "Front desk volunteer"
    description = "Help guests check in and run the evening bonfire."
    role_template = RoleTemplate.VOLUNTEER
    compensation_model = CompensationModel.VOLUNTEER
    start_date = factory.LazyFunction(lambda: in_days(30))
    end_date = factory.LazyFunction(lambda: in_days(60))
    apply_by = factory.LazyFunction(lambda: in_days(20))
    slots = 2
    hours_per_day = 5
    days_per_week = 5
    stay_type = StayType.DORM_BED
    meals = Meals.TWO_MEALS
    wifi = True
    status = GigStatus.DRAFT
