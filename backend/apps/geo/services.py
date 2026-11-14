"""Geocoding with a database cache in front of the geocoder."""

import re
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.geo.geocoders import get_geocoder
from apps.geo.models import GeocodeResult

MIN_QUERY_LENGTH = 5
MAX_QUERY_LENGTH = 300
# "Not found" answers are asked again after this long (maps get better); hits never are.
RETRY_NOT_FOUND_AFTER = timedelta(days=30)


def normalize_query(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip().lower())
    return re.sub(r"\s*,\s*", ", ", text).strip(" ,")[:MAX_QUERY_LENGTH]


def _decimal(value: float) -> Decimal:
    return Decimal(f"{value:.6f}")


def geocode(text: str) -> GeocodeResult:
    """The cached answer for this address, asking the geocoder only on a miss.

    Raises ValueError for queries too short to be an address, and GeocoderUnavailable
    when the geocoder fails (nothing is cached then).
    """
    query = normalize_query(text)
    if len(query) < MIN_QUERY_LENGTH:
        raise ValueError(f"Enter at least {MIN_QUERY_LENGTH} characters of the address.")
    geocoder = get_geocoder()
    cached = GeocodeResult.objects.filter(provider=geocoder.name, query=query).first()
    if cached and (cached.found or cached.fetched_at > timezone.now() - RETRY_NOT_FOUND_AFTER):
        GeocodeResult.objects.filter(pk=cached.pk).update(hits=F("hits") + 1)
        cached.hits += 1
        return cached

    hit = geocoder.geocode(query)
    values = {
        "found": hit is not None,
        "latitude": _decimal(hit.latitude) if hit else None,
        "longitude": _decimal(hit.longitude) if hit else None,
        "display_name": hit.display_name if hit else "",
        "city": hit.city if hit else "",
        "state": hit.state if hit else "",
        "postcode": hit.postcode if hit else "",
        "fetched_at": timezone.now(),
    }
    try:
        with transaction.atomic():
            result, _ = GeocodeResult.objects.update_or_create(
                provider=geocoder.name, query=query, defaults=values
            )
    except IntegrityError:  # another request stored the same query first
        result = GeocodeResult.objects.get(provider=geocoder.name, query=query)
    return result
