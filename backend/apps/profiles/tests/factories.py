import datetime

import factory

from apps.accounts.tests.factories import TalentFactory, VendorFactory
from apps.profiles.constants import BusinessType, TalentType
from apps.profiles.models import Skill, TalentProfile, VendorProfile


class SkillFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Skill
        django_get_or_create = ("slug",)

    name = factory.Sequence(lambda n: f"Skill {n}")
    slug = factory.Sequence(lambda n: f"skill-{n}")


class TalentProfileFactory(factory.django.DjangoModelFactory):
    """A complete talent profile. `TalentProfileFactory(bare=True)` has only a name."""

    class Meta:
        model = TalentProfile
        skip_postgeneration_save = True

    class Params:
        bare = factory.Trait(
            bio="",
            talent_type="",
            languages=factory.LazyFunction(list),
            home_city="",
            emergency_contact_name="",
            emergency_contact_phone="",
            date_of_birth=None,
        )

    user = factory.SubFactory(TalentFactory)
    display_name = factory.Sequence(lambda n: f"Talent {n}")
    bio = "Muralist who loves hostels."
    talent_type = TalentType.ARTIST
    languages = factory.LazyFunction(lambda: ["en", "hi"])
    home_city = "Pune"
    emergency_contact_name = "Ravi Rao"
    emergency_contact_phone = "+919811111111"
    date_of_birth = datetime.date(1998, 5, 17)

    @factory.post_generation
    def skills(self, create, extracted, **kwargs):
        if not create:
            return
        if extracted is not None:
            self.skills.set(extracted)
        elif self.bio:  # complete profiles get a skill
            self.skills.add(SkillFactory())


class VendorProfileFactory(factory.django.DjangoModelFactory):
    """A complete vendor profile. `VendorProfileFactory(bare=True)` has only a name."""

    class Meta:
        model = VendorProfile

    class Params:
        bare = factory.Trait(business_type="", contact_name="", city="", state="", about="")

    user = factory.SubFactory(VendorFactory)
    business_name = factory.Sequence(lambda n: f"Hostel {n}")
    business_type = BusinessType.HOSTEL
    contact_name = "Meera Shah"
    city = "Manali"
    state = "Himachal Pradesh"
    about = "A 40-bed hostel by the river."
