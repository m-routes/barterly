"""Creating and changing properties, their location and photos."""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.common.services.audit import log_action
from apps.geo.geocoders import GeocoderUnavailable
from apps.geo.services import geocode
from apps.media.models import MediaFile, MediaStatus
from apps.media.policy import Kind
from apps.properties.models import MAX_PHOTOS, Property, PropertyPhoto

logger = logging.getLogger(__name__)

ADDRESS_FIELDS = ("address", "city", "state", "pincode")
UNUSABLE_MEDIA = (MediaStatus.REJECTED, MediaStatus.QUARANTINED, MediaStatus.PENDING_UPLOAD)


def can_see_exact_location(user, prop: Property) -> bool:
    """The owner and Barterly admins. Guests get it once a booking is confirmed.

    Bookings don't exist yet: when they do, return True here for a user with a
    confirmed booking at this property.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    return user.pk == prop.vendor_id or user.is_admin_role


def save_property(prop: Property, data: dict, *, actor, request=None) -> Property:
    """Create (prop unsaved) or update a property from validated data.

    An address change without a new pin is geocoded once (cached); the vendor then
    confirms or moves the pin. Moving the pin or changing the address un-confirms it
    unless the same request confirms it.
    """
    creating = prop._state.adding
    before = {f: getattr(prop, f) for f in (*ADDRESS_FIELDS, "latitude", "longitude")}
    for name, value in data.items():
        setattr(prop, name, value)

    pin_sent = "latitude" in data or "longitude" in data
    if ("latitude" in data) != ("longitude" in data):
        raise ValidationError({"latitude": ["Send latitude and longitude together."]})
    address_changed = creating or any(before[f] != getattr(prop, f) for f in ADDRESS_FIELDS)
    pin_moved = pin_sent and (
        before["latitude"] != prop.latitude or before["longitude"] != prop.longitude
    )
    if address_changed and not pin_sent:
        _geocode_into(prop)
    if (address_changed or pin_moved) and not data.get("location_confirmed"):
        prop.location_confirmed = False
    if prop.location_confirmed and not prop.has_point:
        raise ValidationError({"location_confirmed": ["Place the pin before confirming it."]})

    prop.full_clean(exclude=["vendor"])
    with transaction.atomic():
        prop.save()
        if creating:
            log_action(actor=actor, action="property.created", obj=prop, request=request)
    return prop


def _geocode_into(prop: Property) -> None:
    query = ", ".join(
        part for part in (prop.address, prop.city, prop.state, prop.pincode, "India") if part
    )
    try:
        result = geocode(query)
    except (ValueError, GeocoderUnavailable) as exc:
        # Not fatal: the vendor can place the pin by hand.
        logger.info("Property address not geocoded", extra={"reason": str(exc)})
        return
    if result.found:
        prop.latitude, prop.longitude = result.latitude, result.longitude


def remove_property(prop: Property, *, actor, request=None) -> None:
    """Soft-delete. Its verification is withdrawn (and its badge, if it was the last)."""
    from apps.verification.services.cases import withdraw_property

    with transaction.atomic():
        prop = Property.objects.select_for_update().get(pk=prop.pk)
        prop.deleted_at = timezone.now()
        prop.save(update_fields=["deleted_at", "updated_at"])
        log_action(
            actor=actor,
            action="property.deleted",
            obj=prop,
            before={"deleted": False},
            after={"deleted": True},
            request=request,
        )
        withdraw_property(prop, actor=actor, request=request)


def add_photo(
    prop: Property,
    *,
    media_id,
    caption: str = "",
    latitude=None,
    longitude=None,
    captured_at=None,
) -> PropertyPhoto:
    """Attach one of the vendor's uploaded photos (from the signed upload flow)."""
    media = (
        MediaFile.objects.filter(pk=media_id, owner_id=prop.vendor_id, kind=Kind.PHOTO)
        .exclude(status__in=UNUSABLE_MEDIA)
        .first()
    )
    if media is None:
        raise ValidationError({"media_id": ["No usable photo upload with that id."]})
    if (latitude is None) != (longitude is None):
        raise ValidationError({"latitude": ["Send latitude and longitude together."]})
    with transaction.atomic():
        Property.objects.select_for_update().get(pk=prop.pk)  # serialize position numbering
        if prop.photos.filter(media=media).exists():
            raise ValidationError({"media_id": ["That photo is already on this property."]})
        if prop.photos.count() >= MAX_PHOTOS:
            raise ValidationError({"media_id": [f"At most {MAX_PHOTOS} photos per property."]})
        last = prop.photos.aggregate(m=Max("position"))["m"]
        return PropertyPhoto.objects.create(
            property=prop,
            media=media,
            position=0 if last is None else last + 1,
            caption=caption,
            latitude=latitude,
            longitude=longitude,
            captured_at=captured_at,
        )
