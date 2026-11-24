"""Broken access control and IDOR, across every endpoint in the OpenAPI schema.

A victim host and talent get a full stay's worth of objects: a property and photo, a
gig, an application with a note, an offer, an agreement version, a booking with escrow,
deliverables, hours, reviews, a payout, an invoice, a conversation and message, media,
a saved search, an applicant filter, a notification and a verification case.

Then every operation in the schema is called by four attackers: an unrelated talent,
an unrelated host, a staff user with no permissions, and nobody (no credentials), with
the victim's ids in the path. The test fails if:

- an anonymous call isn't refused (401/403), unless the endpoint is public by design;
- an object-scoped call (one with a victim's id in the path) succeeds (2xx) or is
  answered with a validation error (400) that could mean the object was found before
  access was checked;
- a list or summary response contains one of the victim's ids;
- anything of the victim's changed by the end.

Endpoints that are public or open to every signed-in user on purpose are listed in
PUBLIC and OPEN with the reason. A new endpoint is covered automatically: if it's
missing access control this test fails until it's fixed (or listed, with a reason).
"""

import json
import re
import uuid
from dataclasses import dataclass
from datetime import date, timedelta

import pytest
import yaml
from django.conf import settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory

pytestmark = pytest.mark.django_db

SCHEMA = settings.BASE_DIR.parent / "web" / "openapi" / "schema.yaml"

# Anyone, signed in or not, by design.
PUBLIC = {
    ("GET", "/api/v1/health/"): "Load balancer probe.",
    ("GET", "/api/v1/meta/"): "Public app config (versions, links).",
    ("GET", "/api/v1/app/version/"): "Supported app versions, checked before sign-in.",
    ("GET", "/api/v1/gigs/public/"): "Public gig listings for the website.",
    ("GET", "/api/v1/gigs/{gig_id}/public/"): "A live gig's public page.",
    (
        "GET",
        "/api/v1/properties/{property_id}/public/",
    ): "Property page, approx. area only.",
    ("GET", "/api/v1/skills/"): "The public skills list.",
    ("POST", "/api/v1/auth/exchange/"): "Sign-in: the Firebase token is the credential.",
    ("POST", "/api/v1/auth/refresh/"): "The refresh token is the credential.",
    ("POST", "/api/v1/auth/logout/"): "Revokes the refresh token it's given.",
    ("POST", "/api/v1/billing/webhooks/razorpay/"): "Signed webhook.",
    ("POST", "/api/v1/money/webhooks/razorpay/"): "Signed webhook.",
    ("POST", "/api/v1/money/webhooks/razorpayx/"): "Signed webhook.",
    ("POST", "/api/v1/verification/webhooks/kyc/"): "Signed webhook.",
    ("POST", "/api/v1/agreements/webhooks/esign/"): "Signed webhook.",
    ("POST", "/api/v1/jobs/{job}/"): "Cloud Scheduler: an OIDC token is the credential.",
    ("POST", "/api/v1/tasks/{name}/"): "Cloud Tasks: an OIDC token is the credential.",
}

# Any signed-in user may read these, whoever's ids are in them, by design.
OPEN = {
    ("GET", "/api/v1/users/{user_id}/reputation/"): "Reputation is shown to everyone.",
    ("GET", "/api/v1/users/{user_id}/reviews/"): "Published reviews are public.",
    ("GET", "/api/v1/gigs/{gig_id}/"): "A live gig's detail, for applying.",
    ("GET", "/api/v1/gigs/"): "Discovery: live gigs only.",
    ("GET", "/api/v1/attendance/keys/"): "Public keys for verifying check-in passes.",
    ("POST", "/api/v1/reviews/{review_id}/report/"): "Anyone can report a public review.",
    ("POST", "/api/v1/gigs/{gig_id}/applications/"): "Talent apply to live gigs.",
    ("POST", "/api/v1/gigs/{gig_id}/save/"): "Talent save live gigs.",
    ("DELETE", "/api/v1/gigs/{gig_id}/save/"): "Talent unsave gigs.",
}

# Signed-in responses that may contain a victim id, by design (only public data).
LEAK_OK = {
    "GET /api/v1/gigs/",
    "GET /api/v1/gigs/{gig_id}/",
    "GET /api/v1/gigs/public/",
    "GET /api/v1/gigs/{gig_id}/public/",
    "GET /api/v1/properties/{property_id}/public/",
    "GET /api/v1/users/{user_id}/reviews/",
    "GET /api/v1/users/{user_id}/reputation/",
    "POST /api/v1/gigs/{gig_id}/applications/",
    "POST /api/v1/gigs/{gig_id}/save/",
}

REFUSED = {401, 403, 404, 405}
METHODS = ("get", "post", "put", "patch", "delete")


@dataclass
class World:
    ids: dict[str, str]
    snapshot: dict


def operations():
    schema = yaml.safe_load(SCHEMA.read_text())
    for path, item in schema["paths"].items():
        for method in METHODS:
            if method in item:
                yield method.upper(), path, item[method]


def build_world() -> World:
    """Every kind of object an endpoint can name, owned by the victims."""
    from apps.accounts.models import Role
    from apps.agreements.models import AgreementVersion
    from apps.applications.tests.helpers import live_gig
    from apps.attendance import services as attendance
    from apps.billing.models import Invoice, Subscription
    from apps.billing.tests.helpers import plans_on_sale
    from apps.bookings.lifecycle import Actor, BookingStatus
    from apps.bookings.services import transition
    from apps.bookings.tests.helpers import booked
    from apps.chat import services as chat
    from apps.deliverables.models import Deliverable
    from apps.discovery.models import SavedSearch
    from apps.gigs.constants import CompensationModel
    from apps.hiring.models import ApplicationNote, SavedApplicantFilter
    from apps.money import deliverables as single_submissions
    from apps.money import payouts
    from apps.money.models import Payout, PayoutRun
    from apps.money.tests.helpers import check_in, funded, payout_account
    from apps.notifications.models import Notification
    from apps.offers.models import Offer
    from apps.properties.models import PropertyPhoto
    from apps.reviews.models import Review
    from apps.verification.tests.factories import CaseFactory, MediaFileFactory

    def at(day, hour=10):
        return timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()))

    # A paid stay: escrow funded, checked in, work handed in, released, paid out.
    paid = booked(
        live_gig(compensation_model=CompensationModel.PAID, stipend_amount=5000,
                 stipend_period="total", stay_type="none")
    )  # fmt: skip
    host, talent = paid.vendor, paid.talent
    paid, escrow = funded(paid)
    payout_account(talent)
    check_in(paid)
    submission = single_submissions.submit(paid.pk, talent=talent, note="Done")
    single_submissions.review(submission.pk, vendor=host, approve=True)
    escrow.refresh_from_db()
    payouts.pay(escrow.pk)
    payout = Payout.objects.get(escrow=escrow)
    run = PayoutRun.objects.create(trigger="admin")

    # A barter stay at the same host, completed and reviewed both ways.
    barter = booked(
        live_gig(compensation_model=CompensationModel.BARTER, vendor=host,
                 property=paid.gig.property,
                 deliverables=[{"type": "instagram_reel", "quantity": 1}]),
        talent=talent, proposed_start=paid.end_date + timedelta(days=2),
        proposed_end=paid.end_date + timedelta(days=9),
    )  # fmt: skip
    start = at(barter.start_date)
    for to, who, user in ((BookingStatus.CHECKED_IN, Actor.VENDOR, host),
                          (BookingStatus.DELIVERING, Actor.TALENT, talent),
                          (BookingStatus.COMPLETED, Actor.VENDOR, host)):  # fmt: skip
        transition(barter.pk, to, actor=who, user=user, now=start)
    barter.refresh_from_db()
    deliverable = Deliverable.objects.filter(booking=barter).first()
    from apps.reviews import services as reviews

    review = reviews.submit(barter.pk, author=talent, rating=5,
                            text="A lovely place to work and stay.", communication=5,
                            accuracy=5, safety=5, reliability=5)  # fmt: skip
    reviews.submit(barter.pk, author=host, rating=5, text="Great work, on time, kind.",
                   communication=5, accuracy=5, safety=5, reliability=5)  # fmt: skip
    review = Review.objects.get(pk=review.pk)
    log = attendance  # hour logs need a checked-in stay; use the paid one
    from apps.attendance import hours

    entry, _ = hours.log(paid.pk, talent=talent, day=paid.start_date, minutes=60,
                         now=at(paid.start_date))  # fmt: skip
    check = attendance.CheckIn.objects.get(booking=paid)

    application = paid.application
    offer = Offer.objects.filter(application=application).first()
    version = AgreementVersion.objects.filter(agreement__booking=paid).first()
    conversation = chat.open_conversation(application, "vendor", user=host)
    message = chat.send(conversation.pk, sender=host, body="See you soon").message
    note = ApplicationNote.objects.create(application=application, author=host, body="Good")
    saved_filter = SavedApplicantFilter.objects.create(vendor=host, gig=paid.gig, name="Mine",
                                                       params={})  # fmt: skip
    search = SavedSearch.objects.create(
        talent=talent, name="Goa", params={}, last_checked_at=timezone.now()
    )
    notification = Notification.objects.create(user=talent, kind="booking.confirmed",
                                               title="Hi", body="Hi")  # fmt: skip
    media = MediaFileFactory(owner=talent)
    photo_media = MediaFileFactory(owner=host)
    photo = PropertyPhoto.objects.create(property=paid.gig.property, media=photo_media)
    case = CaseFactory(user=host)
    plans = plans_on_sale()
    subscription = Subscription.objects.create(vendor=host, plan=plans["growth"], status="active",
                                               gateway_subscription_id="sub_victim")  # fmt: skip
    invoice = Invoice.objects.create(
        number="BRT/2026-27/000001", vendor=host, subscription=subscription,
        gateway_payment_id="pay_victim", plan_name="Growth", taxable_paise=100, igst_paise=18,
        total_paise=118, gst_rate_percent=18, sac_code="998314", place_of_supply="Goa",
        supplier={}, buyer_name="Victim", issued_at=timezone.now(),
    )  # fmt: skip

    assert host.role == Role.VENDOR and talent.role == Role.TALENT
    ids = {
        "booking_id": str(paid.pk),
        "application_id": str(application.pk),
        "gig_id": str(paid.gig_id),
        "property_id": str(paid.gig.property_id),
        "conversation_id": str(conversation.pk),
        "deliverable_id": str(deliverable.pk),
        "review_id": str(review.pk),
        "version_id": str(version.pk),
        "offer_id": str(offer.pk),
        "user_id": str(talent.pk),
        "case_id": str(case.pk),
        "check_in_id": str(check.pk),
        "run_id": str(run.pk),
        "payout_id": str(payout.pk),
        "agreement_id": str(version.agreement_id),
        "filter_id": str(saved_filter.pk),
        "note_id": str(note.pk),
        "invoice_id": str(invoice.pk),
        "submission_id": str(submission.pk),
        "search_id": str(search.pk),
        "log_id": str(entry.pk),
        "media_id": str(media.pk),
        "message_id": str(message.pk),
        "notification_id": str(notification.pk),
        "photo_id": str(photo.pk),
        # Values, not objects.
        "fy": "2026-27",
        "kind": "csv",
        "job": "expire_offers",
        "key": "escrow_funding",
        "name": "dispatch",
    }
    del log
    return World(ids=ids, snapshot=snapshot(ids, host, talent))


def snapshot(ids, host, talent) -> dict:
    """What an attacker must not be able to change."""
    from apps.applications.models import Application
    from apps.bookings.models import Booking
    from apps.deliverables.models import Deliverable
    from apps.gigs.models import Gig
    from apps.hiring.models import ApplicationNote
    from apps.money.models import Escrow
    from apps.notifications.models import Notification
    from apps.profiles.models import TalentProfile
    from apps.properties.models import Property

    def rows(model, **filters):
        return sorted(
            (str(r["pk"]), r["fingerprint"])
            for r in [
                {"pk": o.pk, "fingerprint": repr(sorted(o.__dict__.items(), key=str)[:40])}
                for o in model.objects.filter(**filters)
            ]
        )

    return {
        "bookings": list(Booking.objects.filter(vendor=host).values_list("pk", "status")),
        "applications": list(Application.objects.filter(talent=talent).values_list("pk", "status")),
        "gigs": list(Gig.objects.filter(vendor=host).values_list("pk", "status", "title")),
        "properties": list(Property.all_objects.filter(vendor=host).values_list("pk", "name"))
        if hasattr(Property, "all_objects")
        else list(Property.objects.filter(vendor=host).values_list("pk", "name")),
        "escrow": list(Escrow.objects.values_list("pk", "status", "released_paise")),
        "deliverables": list(Deliverable.objects.values_list("pk", "status", "due_date")),
        "notes": list(ApplicationNote.objects.values_list("pk", "body")),
        "notifications": list(Notification.objects.filter(user=talent).values_list("pk", "status")),
        "profile": list(TalentProfile.objects.filter(user=talent).values_list("pk", "bio")),
    }


def attackers():
    return {
        "other talent": TalentFactory(),
        "other host": VendorFactory(),
        "staff without permissions": AdminUserFactory(),
        "anonymous": None,
    }


def plausible(node, components, ids, depth=0):
    """A body that passes validation where it can, so the request reaches the access
    check: required fields filled with values of the right type."""
    if depth > 6:
        return None
    if "$ref" in node:
        return plausible(components[node["$ref"].rsplit("/", 1)[1]], components, ids, depth + 1)
    for key in ("allOf", "oneOf"):
        if node.get(key):
            return plausible(node[key][0], components, ids, depth + 1)
    if "enum" in node:
        return next((v for v in node["enum"] if v not in ("", None)), node["enum"][0])
    kind, fmt = node.get("type"), node.get("format")
    if kind == "object" or "properties" in node:
        props = node.get("properties") or {}
        return {
            k: plausible(v, components, ids, depth + 1)
            for k, v in props.items()
            if k in (node.get("required") or []) and not v.get("readOnly")
        }
    if kind == "array":
        return []
    if kind == "integer":
        return max(1, node.get("minimum", 1))
    if kind == "number":
        return 1
    if kind == "boolean":
        return True
    if fmt == "uuid":
        return ids.get("booking_id")
    if fmt == "date":
        return str(timezone.localdate())
    if fmt == "date-time":
        return timezone.now().isoformat()
    if fmt == "uri":
        return "https://example.com/x"
    if fmt == "decimal":
        return "1.00"
    return "Plausible text for this field."[: node.get("maxLength", 40)]


def body_for(op, components, ids):
    content = (op.get("requestBody") or {}).get("content", {})
    schema = (content.get("application/json") or {}).get("schema")
    return plausible(schema, components, ids) if schema else {}


def call(client, method, path, ids, body):
    url = re.sub(r"\{(\w+)\}", lambda m: ids.get(m[1], str(uuid.uuid4())), path)
    return client.generic(method, url, data=json.dumps(body), content_type="application/json")


def strangers(ids):
    """The same ids with every object id swapped for one that doesn't exist."""
    return {k: (v if k in VALUES else str(uuid.uuid4())) for k, v in ids.items()}


VALUES = {"fy", "kind", "job", "name"}


def victim_ids(world: World) -> set[str]:
    # UUIDs only: small integer ids would match any number in a response.
    return {v for k, v in world.ids.items() if k not in VALUES and len(v) == 36}


@pytest.fixture
def midday():
    """Hold the clock at midday IST: a run that straddles midnight would otherwise see
    date-based state (what's due, what's expired) change between snapshots."""
    from datetime import datetime, time
    from unittest import mock
    from zoneinfo import ZoneInfo

    from django.utils import timezone

    real_now = timezone.now
    noon = datetime.combine(
        real_now().astimezone(ZoneInfo("Asia/Kolkata")).date(),
        time(12),
        tzinfo=ZoneInfo("Asia/Kolkata"),
    )
    start = real_now()
    with mock.patch.object(timezone, "now", lambda: noon + (real_now() - start)):
        yield


def test_every_endpoint_refuses_other_peoples_objects(midday):
    world = build_world()
    components = yaml.safe_load(SCHEMA.read_text())["components"]["schemas"]
    ours = victim_ids(world)
    problems: list[str] = []
    for who, user in attackers().items():
        client = APIClient()
        if user is not None:
            client.force_authenticate(user)
        for method, path, op in operations():
            key = (method, path)
            body = body_for(op, components, world.ids)
            response = call(client, method, path, world.ids, body)
            status = response.status_code
            if user is None:
                if key not in PUBLIC and status not in (401, 403):
                    problems.append(f"{who}: {method} {path} → {status} (expected 401)")
                continue
            scoped = "_id}" in path
            if key not in PUBLIC and key not in OPEN and scoped and status not in REFUSED:
                # Refused for a reason other than access (a validation error, a state
                # check)? Fine only if a made-up id gets exactly the same answer: then
                # nothing was found or learned about the victim's object.
                same = call(client, method, path, strangers(world.ids), body)
                if status < 300 or (same.status_code, same.content) != (
                    status,
                    response.content,
                ):
                    problems.append(
                        f"{who}: {method} {path} → {status} on someone else's object "
                        f"(a made-up id gets {same.status_code})"
                    )
            if f"{method} {path}" not in LEAK_OK and status < 300:
                body = response.content.decode(errors="ignore")
                leaked = sorted(i for i in ours if i in body)
                if leaked:
                    problems.append(f"{who}: {method} {path} leaks {', '.join(leaked)}")
    assert not problems, "\n".join(problems)
    # Nothing of the victim's changed.
    from apps.bookings.models import Booking

    host = Booking.objects.get(pk=world.ids["booking_id"]).vendor
    talent = Booking.objects.get(pk=world.ids["booking_id"]).talent
    assert snapshot(world.ids, host, talent) == world.snapshot


def test_request_bodies_are_size_limited():
    """Every string field a client can send has a maxLength, every list a maxItems
    (ASVS 5.1.4, 13.1.x). Free-form JSON objects are listed with a reason."""
    schema = yaml.safe_load(SCHEMA.read_text())
    components = schema["components"]["schemas"]
    exempt = {
        # Webhook bodies are the provider's JSON; Django caps the request size.
        "object",
    }
    problems = []

    def walk(name, node, seen):
        if "$ref" in node:
            ref = node["$ref"].rsplit("/", 1)[1]
            if ref not in seen:
                walk(ref, components[ref], seen | {ref})
            return
        for part in node.get("allOf", []) + node.get("oneOf", []):
            walk(name, part, seen)
        kind = node.get("type")
        if node.get("readOnly"):
            return
        if (
            kind == "string"
            and "enum" not in node
            and node.get("format")
            not in (
                "date",
                "date-time",
                "uuid",
                "binary",
                "decimal",
                "time",
                "email",
            )
            and "maxLength" not in node
            and "pattern" not in node
        ):
            problems.append(f"{name}: a string without maxLength")
        if kind == "array":
            if "maxItems" not in node:
                problems.append(f"{name}: a list without maxItems")
            walk(name, node.get("items", {}), seen)
        for prop, child in (node.get("properties") or {}).items():
            walk(f"{name}.{prop}", child, seen)

    for method, path, op in operations():
        body = (op.get("requestBody") or {}).get("content", {}).get("application/json")
        if not body:
            continue
        schema_node = body["schema"]
        if schema_node.get("type") in exempt and "properties" not in schema_node:
            continue
        walk(f"{method} {path}", schema_node, set())
    assert not sorted(set(problems)), "\n".join(sorted(set(problems)))


def test_upload_and_body_limits():
    assert settings.DATA_UPLOAD_MAX_MEMORY_SIZE <= 2.5 * 1024 * 1024
    assert settings.DATA_UPLOAD_MAX_NUMBER_FIELDS <= 1000
    date.today()  # keep the import honest
