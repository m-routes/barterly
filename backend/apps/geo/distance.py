"""Distances on plain latitude/longitude columns (no PostGIS).

Nearby queries filter on a bounding box first, which the (latitude, longitude) index
can serve, then on the exact haversine distance.
"""

import math
from dataclasses import dataclass

EARTH_RADIUS_M = 6_371_000
METRES_PER_DEGREE_LAT = 111_320


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(min(1.0, a)))


@dataclass(frozen=True)
class BoundingBox:
    min_lat: float
    max_lat: float
    min_lng: float
    max_lng: float


def bounding_box(lat: float, lng: float, radius_m: float) -> BoundingBox:
    """The smallest lat/lng box that contains every point within radius_m of (lat, lng)."""
    d_lat = radius_m / METRES_PER_DEGREE_LAT
    cos_lat = max(math.cos(math.radians(lat)), 1e-6)
    d_lng = radius_m / (METRES_PER_DEGREE_LAT * cos_lat)
    return BoundingBox(
        min_lat=max(lat - d_lat, -90.0),
        max_lat=min(lat + d_lat, 90.0),
        min_lng=lng - d_lng,
        max_lng=lng + d_lng,
    )


def offset(lat: float, lng: float, *, north_m: float, east_m: float) -> tuple[float, float]:
    """The point north_m metres north and east_m metres east of (lat, lng)."""
    d_lat = north_m / METRES_PER_DEGREE_LAT
    d_lng = east_m / (METRES_PER_DEGREE_LAT * max(math.cos(math.radians(lat)), 1e-6))
    return lat + d_lat, lng + d_lng
