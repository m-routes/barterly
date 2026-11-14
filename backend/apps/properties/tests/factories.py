from decimal import Decimal

import factory

from apps.accounts.tests.factories import VendorFactory
from apps.properties.models import Property, PropertyPhoto, PropertyType
from apps.verification.tests.factories import PIN, MediaFileFactory


class PropertyFactory(factory.django.DjangoModelFactory):
    """A property in Manali with a confirmed pin."""

    class Meta:
        model = Property

    vendor = factory.SubFactory(VendorFactory)
    name = factory.Sequence(lambda n: f"River Hostel {n}")
    property_type = PropertyType.HOSTEL
    address = "Old Manali Road, near the bridge"
    city = "Manali"
    state = "Himachal Pradesh"
    pincode = "175131"
    latitude = Decimal(str(PIN["latitude"]))
    longitude = Decimal(str(PIN["longitude"]))
    location_confirmed = True


def add_photos(prop, n=3, *, metres_north=20, located=True):
    """n ready photos taken metres_north of the pin."""
    photos = []
    for i in range(n):
        media = MediaFileFactory(owner=prop.vendor)
        lat = Decimal(str(round(PIN["latitude"] + metres_north / 111_000, 6))) if located else None
        photos.append(
            PropertyPhoto.objects.create(
                property=prop,
                media=media,
                position=i,
                latitude=lat,
                longitude=Decimal(str(PIN["longitude"])) if located else None,
            )
        )
    return photos
