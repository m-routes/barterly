import factory

from apps.accounts.tests.factories import TalentFactory, VendorFactory
from apps.profiles.models import PropertyType, TalentProfile, VendorProfile


class TalentProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TalentProfile

    user = factory.SubFactory(TalentFactory)
    full_name = factory.Sequence(lambda n: f"Talent {n}")
    languages = factory.LazyFunction(lambda: ["English", "Hindi"])


class VendorProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VendorProfile

    user = factory.SubFactory(VendorFactory)
    business_name = factory.Sequence(lambda n: f"Hostel {n}")
    property_type = PropertyType.HOSTEL
    city = "Manali"
    state = "Himachal Pradesh"
