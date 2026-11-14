"""Turning an address into a point.

Geocoders sit behind one interface, named by the code setting GEOCODER. Callers go
through apps.geo.services.geocode(), which caches every answer in the database.

NominatimGeocoder follows the OpenStreetMap Nominatim usage policy
(https://operations.osmfoundation.org/policies/nominatim/):
- an identifying User-Agent (NOMINATIM_USER_AGENT) and optional contact email;
- at most one request per second across all our instances (a shared cache slot);
- results cached in our database; no repeat lookups for the same query;
- no autocomplete: we geocode only when a vendor saves an address or presses
  "find on map", never on each keystroke.
"""

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from typing import Protocol

from django.conf import settings
from django.core.cache import cache as django_cache
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GeocodeHit:
    latitude: float
    longitude: float
    display_name: str = ""
    city: str = ""
    state: str = ""
    postcode: str = ""


class GeocoderUnavailable(Exception):
    """The geocoder failed, timed out, or is busy. Try again later; nothing is cached."""


class Geocoder(Protocol):
    name: str

    def geocode(self, query: str) -> GeocodeHit | None:
        """The best match in India, or None when nothing matches."""
        ...


class RateLimiter:
    """At most one call per `interval` seconds across every process sharing the cache."""

    def __init__(
        self,
        key: str,
        *,
        interval: int = 1,
        max_wait: float = 5.0,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.key, self.interval, self.max_wait = key, interval, max_wait
        self.sleep, self.clock = sleep, clock

    def acquire(self) -> None:
        deadline = self.clock() + self.max_wait
        # cache.add only succeeds when the key is absent, so one caller per interval wins.
        while not django_cache.add(self.key, 1, timeout=self.interval):
            if self.clock() >= deadline:
                raise GeocoderUnavailable("Geocoder is busy; try again in a moment.")
            self.sleep(0.2)


class NominatimGeocoder:
    name = "nominatim"

    def __init__(self, *, limiter: RateLimiter | None = None, opener=None) -> None:
        self.limiter = limiter or RateLimiter("geo:nominatim:slot")
        self.opener = opener or urllib.request.urlopen

    def geocode(self, query: str) -> GeocodeHit | None:
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": "1",
            "countrycodes": "in",
            "addressdetails": "1",
        }
        if settings.NOMINATIM_EMAIL:
            params["email"] = settings.NOMINATIM_EMAIL
        url = f"{settings.NOMINATIM_URL.rstrip('/')}/search?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(  # noqa: S310 (fixed https base URL from settings)
            url,
            headers={"User-Agent": settings.NOMINATIM_USER_AGENT, "Accept-Language": "en"},
        )
        self.limiter.acquire()
        try:
            with self.opener(request, timeout=settings.GEOCODER_TIMEOUT_SECONDS) as response:
                rows = json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            logger.warning("Nominatim lookup failed", extra={"error": str(exc)})
            raise GeocoderUnavailable(str(exc)) from exc
        if not rows:
            return None
        row = rows[0]
        address = row.get("address") or {}
        return GeocodeHit(
            latitude=float(row["lat"]),
            longitude=float(row["lon"]),
            display_name=str(row.get("display_name", ""))[:500],
            city=str(address.get("city") or address.get("town") or address.get("village") or "")[
                :120
            ],
            state=str(address.get("state", ""))[:120],
            postcode=str(address.get("postcode", ""))[:20],
        )


class FakeGeocoder:
    """For tests and offline work: knows a few places, counts its calls."""

    name = "fake"
    PLACES = {
        "manali": GeocodeHit(
            32.2432,
            77.1892,
            "Manali, Kullu, Himachal Pradesh",
            "Manali",
            "Himachal Pradesh",
            "175131",
        ),
        "goa": GeocodeHit(15.5527, 73.7517, "Anjuna, North Goa, Goa", "Anjuna", "Goa", "403509"),
        "rishikesh": GeocodeHit(
            30.0869, 78.2676, "Rishikesh, Uttarakhand", "Rishikesh", "Uttarakhand", "249201"
        ),
    }

    def __init__(self) -> None:
        self.calls: list[str] = []

    def geocode(self, query: str) -> GeocodeHit | None:
        self.calls.append(query)
        return next((hit for name, hit in self.PLACES.items() if name in query), None)


@cache
def _build(path: str) -> Geocoder:
    return import_string(path)()


def get_geocoder() -> Geocoder:
    return _build(settings.GEOCODER)
