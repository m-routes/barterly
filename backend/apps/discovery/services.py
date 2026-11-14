"""Gig discovery for talent: hard filters in SQL, then the fit score, then a cursor page.

Hard filters (live, still taking applications, dates, location, eligibility) decide
what a talent may see at all. The fit score only orders what is left.
"""

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from django.conf import settings
from django.contrib.postgres.search import SearchQuery
from django.db.models import Exists, OuterRef, Prefetch, Q, prefetch_related_objects
from django.utils import timezone

from apps.discovery.filters import Sort
from apps.discovery.scoring import FitResult, GigFacts, TalentFacts, fit_score
from apps.gigs.constants import GigStatus
from apps.gigs.models import SEARCH_CONFIG, Gig
from apps.profiles.models import TalentProfile
from apps.properties.models import PropertyPhoto, distance_m_expression, in_bounding_box
from apps.verification.constants import BadgeKind, CaseStatus
from apps.verification.models import Badge


class InvalidCursor(ValueError):
    """The cursor is malformed or belongs to a different sort."""


@dataclass(frozen=True)
class Eligibility:
    languages: tuple[str, ...]
    followers: int


@dataclass
class ScoredGig:
    gig: Gig
    fit: FitResult
    distance_km: float | None


@dataclass
class SearchPage:
    results: list[ScoredGig]
    next_cursor: str | None


# --- Facts about the talent ---


def talent_profile(user) -> TalentProfile | None:
    return (
        TalentProfile.objects.filter(user=user).prefetch_related("skills").first()
        if user.is_authenticated
        else None
    )


def talent_signals(user) -> dict:
    """Reliability, rating and audience quality. Bookings and reviews (Phase 3) will
    fill these in; until then they are unknown, which scores as neutral."""
    return {"reliability": None, "rating": None, "audience_quality": None}


def talent_facts(profile: TalentProfile | None, signals: dict, params: dict) -> TalentFacts:
    return TalentFacts(
        skills=frozenset(s.slug for s in profile.skills.all()) if profile else frozenset(),
        reliability=signals["reliability"],
        rating=signals["rating"],
        audience_quality=signals["audience_quality"],
        available_from=params.get("start_from"),
        available_to=params.get("start_to"),
    )


def eligibility_for(profile: TalentProfile | None) -> Eligibility:
    """Unknown follower counts count as zero: a hard filter can't be neutral."""
    if profile is None:
        return Eligibility(languages=(), followers=0)
    return Eligibility(
        languages=tuple(profile.languages or ()), followers=profile.instagram_followers or 0
    )


# --- Hard filters ---


def live_gigs():
    """Every gig a talent may see, before their filters."""
    id_verified = Badge.objects.filter(
        user=OuterRef("vendor_id"), kind=BadgeKind.ID_VERIFIED, revoked_at__isnull=True
    )
    return (
        Gig.objects.filter(
            status=GigStatus.LIVE,
            apply_by__gte=timezone.localdate(),
            property__deleted_at__isnull=True,
        )
        .select_related("property")
        .annotate(vendor_id_verified=Exists(id_verified))
    )


def filtered(params: dict, eligibility: Eligibility):
    qs = live_gigs()
    if params.get("compensation_model"):
        qs = qs.filter(compensation_model__in=params["compensation_model"])
    if params.get("role"):
        qs = qs.filter(role_template__in=params["role"])
    if params.get("stay_type"):
        qs = qs.filter(stay_type__in=params["stay_type"])
    if params.get("city"):
        qs = qs.filter(property__city__iexact=params["city"].strip())
    if params.get("start_from"):
        qs = qs.filter(start_date__gte=params["start_from"])
    if params.get("start_to"):
        qs = qs.filter(start_date__lte=params["start_to"])
    if params.get("women_friendly"):
        qs = qs.filter(property__women_friendly=True)
    if params.get("verified_hosts"):
        qs = qs.filter(property__verification_status=CaseStatus.APPROVED, vendor_id_verified=True)
    if params.get("min_stay"):
        qs = qs.filter(Q(min_stay_days__isnull=True) | Q(min_stay_days__lte=params["min_stay"]))
    if params.get("q"):
        query = SearchQuery(params["q"], search_type="websearch", config=SEARCH_CONFIG)
        qs = qs.filter(search_vector=query)

    if "latitude" in params:
        lat, lng = params["latitude"], params["longitude"]
        qs = qs.annotate(
            distance_m=distance_m_expression(
                "property__approx_latitude", "property__approx_longitude", lat, lng
            )
        )
        if params.get("radius_km"):
            radius_m = params["radius_km"] * 1000
            qs = qs.filter(
                in_bounding_box(
                    "property__approx_latitude", "property__approx_longitude", lat, lng, radius_m
                ),
                distance_m__lte=radius_m,
            )
        elif params.get("sort") == Sort.DISTANCE:
            qs = qs.filter(property__approx_latitude__isnull=False)

    # Eligibility: the talent must meet the gig's own requirements.
    languages = list(eligibility.languages)
    language_ok = Q(languages=[])
    if languages:
        language_ok |= Q(languages__has_any_keys=languages)
    qs = qs.filter(language_ok)
    qs = qs.filter(Q(min_followers__isnull=True) | Q(min_followers__lte=eligibility.followers))
    return qs


# --- Scoring ---


def score(gig: Gig, talent: TalentFacts) -> ScoredGig:
    distance_m = getattr(gig, "distance_m", None)
    distance_km = None if distance_m is None else distance_m / 1000
    end = gig.end_date
    if end is None and gig.start_date and gig.duration_days:
        end = gig.start_date + timedelta(days=gig.duration_days)
    facts = GigFacts(
        skills=frozenset(s.slug for s in gig.skills.all()),
        start_date=gig.start_date,
        end_date=end,
        distance_km=distance_km,
    )
    fit = fit_score(
        talent,
        facts,
        weights=settings.DISCOVERY_FIT_WEIGHTS,
        distance_zero_km=settings.DISCOVERY_DISTANCE_ZERO_KM,
    )
    return ScoredGig(gig=gig, fit=fit, distance_km=distance_km)


# --- Cursor pages ---

DB_ORDER = {
    Sort.NEWEST: ("published_at", "desc"),
    Sort.START_DATE: ("start_date", "asc"),
    Sort.DISTANCE: ("distance_m", "asc"),
}


def encode_cursor(sort: str, key, gig_id) -> str:
    if isinstance(key, datetime | date):
        key = key.isoformat()
    raw = json.dumps({"s": sort, "k": key, "id": str(gig_id)}).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, sort: str) -> tuple:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded))
        key, gig_id = data["k"], data["id"]
    except (ValueError, KeyError, TypeError, binascii.Error) as exc:
        raise InvalidCursor("Malformed cursor.") from exc
    if data.get("s") != sort:
        raise InvalidCursor("This cursor belongs to a different sort.")
    if sort == Sort.NEWEST:
        key = datetime.fromisoformat(key)
    elif sort == Sort.START_DATE:
        key = date.fromisoformat(key)
    return key, gig_id


def search(user, params: dict, *, cursor: str | None = None, page_size: int | None = None):
    page_size = page_size or settings.DISCOVERY_PAGE_SIZE
    profile = talent_profile(user)
    talent = talent_facts(profile, talent_signals(user), params)
    qs = filtered(params, eligibility_for(profile)).prefetch_related("skills")
    sort = params.get("sort", Sort.BEST_FIT)

    if sort == Sort.BEST_FIT:
        candidates = qs.order_by("-published_at", "-id")[: settings.DISCOVERY_MAX_CANDIDATES]
        scored = sorted(
            (score(g, talent) for g in candidates), key=lambda s: (-s.fit.score, str(s.gig.pk))
        )
        if cursor:
            key, after = decode_cursor(cursor, sort)
            scored = [s for s in scored if (-s.fit.score, str(s.gig.pk)) > (-int(key), after)]
        page = scored[: page_size + 1]
    else:
        field, direction = DB_ORDER[sort]
        descending = direction == "desc"
        qs = qs.order_by(f"-{field}", "-id") if descending else qs.order_by(field, "id")
        if cursor:
            key, after = decode_cursor(cursor, sort)
            op = "lt" if descending else "gt"
            qs = qs.filter(Q(**{f"{field}__{op}": key}) | Q(**{field: key, f"id__{op}": after}))
        page = [score(g, talent) for g in qs[: page_size + 1]]

    has_more = len(page) > page_size
    page = page[:page_size]
    prefetch_related_objects(
        [s.gig for s in page],
        Prefetch(
            "property__photos",
            queryset=PropertyPhoto.objects.select_related("media").order_by("position"),
        ),
    )
    next_cursor = None
    if has_more:
        last = page[-1]
        key = last.fit.score if sort == Sort.BEST_FIT else getattr(last.gig, DB_ORDER[sort][0])
        next_cursor = encode_cursor(sort, key, last.gig.pk)
    return SearchPage(results=page, next_cursor=next_cursor)
