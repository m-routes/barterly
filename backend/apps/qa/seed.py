"""Realistic acceptance-test data for staging (manage.py seed_staging).

What it makes, all through the same services the app uses, so every record is one
the app could have made itself:

- the personas in qa/personas.json (Firebase test numbers), with complete profiles,
  verified IDs and businesses, a property each, and an admin;
- extra vendors with their business check in every verification state;
- gigs in every status, applications in every status, and bookings at every stage:
  signing, confirmed, checked in, delivering (deliverables handed in, approved, with
  changes asked), completed and paid out, reviewed, cancelled late by the host, no-show
  and disputed;
- paid bookings with escrow funded through the payment webhook path (stand-in
  gateway, ids prefixed seed_), released and paid out.

Bookings are built with near-future dates (the rules refuse past ones), then their
dates are moved back so the history reads naturally (a checked-in stay started
yesterday, not next week).

Each run is a new batch: extra people get fresh phone numbers, and personas are
reused. Signatures and payments go through stand-ins (apps.qa.providers), so nothing
reaches Razorpay or sends a code. It refuses to run where settings.ALLOW_SEED is off
(production).
"""

import datetime
import json
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User

PERSONAS_FILE = Path(__file__).with_name("personas.json")
EXTRA_PHONE_PREFIX = "+9190001"  # +91 90001 BB NNN: batch BB, person NNN


class SeedRefused(Exception):
    pass


def load_personas(path: Path = PERSONAS_FILE) -> dict[str, dict]:
    data = json.loads(path.read_text())
    return {k: v for k, v in data.items() if not k.startswith("_")}


def today() -> datetime.date:
    return timezone.localdate()


def days(n: int) -> datetime.date:
    return today() + datetime.timedelta(days=n)


@dataclass
class SeedReport:
    batch: int
    personas: dict[str, str] = field(default_factory=dict)
    counts: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, kind: str, status: str) -> None:
        self.counts.setdefault(kind, {}).setdefault(status, 0)
        self.counts[kind][status] += 1


class Seeder:
    def __init__(self, *, batch: int | None = None, personas: dict | None = None):
        if not getattr(settings, "ALLOW_SEED", False):
            raise SeedRefused("Seeding is switched off here (settings.ALLOW_SEED).")
        self.personas = personas or load_personas()
        self.batch = batch if batch is not None else self._next_batch()
        self.report = SeedReport(batch=self.batch)
        self._extra = 0
        self.users: dict[str, User] = {}

    # ---------- people ----------

    def _next_batch(self) -> int:
        used = User.objects.filter(phone__startswith=EXTRA_PHONE_PREFIX).values_list(
            "phone", flat=True
        )
        batches = {int(p[len(EXTRA_PHONE_PREFIX) : len(EXTRA_PHONE_PREFIX) + 2]) for p in used}
        return (max(batches) + 1) % 100 if batches else 1

    def _extra_phone(self) -> str:
        self._extra += 1
        return f"{EXTRA_PHONE_PREFIX}{self.batch:02d}{self._extra:03d}"

    def persona(self, key: str) -> User:
        if key in self.users:
            return self.users[key]
        spec = self.personas[key]
        user = User.objects.filter(phone=spec["phone"]).first()
        if user is None:
            user = User.objects.create_user(spec["phone"], role=spec["role"])
        if spec["role"] == Role.VENDOR:
            self._vendor_profile(user, spec)
            self._on_plan(user, "pro")
        elif spec["role"] == Role.TALENT:
            self._talent_profile(user, spec)
        elif spec["role"] == Role.ADMIN:
            self._admin(user, spec)
        self.users[key] = user
        self.report.personas[key] = spec["phone"]
        return user

    def _admin(self, user: User, spec: dict) -> None:
        from apps.backoffice.roles import sync_roles

        user.role, user.is_staff = Role.ADMIN, True
        password = getattr(settings, "SEED_ADMIN_PASSWORD", "")
        if password:  # back-office sign-in for the acceptance suite; from the environment
            user.set_password(password)
        user.save()
        sync_roles()
        user.groups.add(*Group.objects.filter(name__in=spec.get("admin_roles", [])))

    def _vendor_profile(self, user: User, spec: dict):
        from apps.profiles.models import VendorProfile

        profile, _ = VendorProfile.objects.update_or_create(
            user=user,
            defaults={
                "business_name": spec["business_name"],
                "business_type": spec["business_type"],
                "contact_name": spec["name"],
                "city": spec["city"],
                "state": spec["state"],
                "about": f"{spec['business_name']} in {spec['city']}. Seeded for testing.",
            },
        )
        return profile

    def _on_plan(self, vendor: User, code: str) -> None:
        """An active subscription (as if paid at checkout), so the persona can run many
        live gigs like a real paying host."""
        from apps.billing.models import Plan, Subscription

        if Subscription.objects.filter(vendor=vendor, status="active").exists():
            return
        Subscription.objects.create(
            vendor=vendor,
            plan=Plan.objects.get(code=code),
            status="active",
            gateway_subscription_id=f"seed_sub_{vendor.pk.hex}",
            current_period_start=timezone.now(),
            current_period_end=timezone.now() + datetime.timedelta(days=365),
        )

    def _talent_profile(self, user: User, spec: dict):
        from apps.profiles.models import Skill, TalentProfile

        profile, _ = TalentProfile.objects.update_or_create(
            user=user,
            defaults={
                "display_name": spec["name"],
                "bio": "Seeded for acceptance testing. Loves hostels and long walks.",
                "talent_type": spec["talent_type"],
                "languages": ["en", "hi"],
                "home_city": spec.get("home_city", "Pune"),
                "emergency_contact_name": "Asha (seed)",
                "emergency_contact_phone": "+919811100000",
                "date_of_birth": datetime.date(1997, 3, 14),
                "instagram_handle": spec.get("instagram_handle", ""),
                "instagram_followers": spec.get("instagram_followers"),
            },
        )
        skill, _ = Skill.objects.get_or_create(slug="front-desk", defaults={"name": "Front desk"})
        profile.skills.add(skill)
        self._id_badge(user)
        return profile

    def _id_badge(self, user: User) -> None:
        from apps.verification.constants import BadgeKind
        from apps.verification.services.cases import active_badge_kinds, grant_badge

        if BadgeKind.ID_VERIFIED not in active_badge_kinds(user):
            grant_badge(user, BadgeKind.ID_VERIFIED, reason="Seeded for acceptance testing.")

    def extra_talent(self, name: str) -> User:
        spec = {
            "role": Role.TALENT,
            "phone": self._extra_phone(),
            "name": name,
            "talent_type": "hospitality",
        }
        user = User.objects.create_user(spec["phone"], role=Role.TALENT)
        self._talent_profile(user, spec)
        return user

    def extra_vendor(self, name: str, business: str) -> User:
        spec = {
            **self.personas["hostel_owner"],
            "phone": self._extra_phone(),
            "name": name,
            "business_name": business,
        }
        user = User.objects.create_user(spec["phone"], role=Role.VENDOR)
        self._vendor_profile(user, spec)
        return user

    # ---------- verification ----------

    def business_case(self, vendor: User, status: str):
        """The vendor's business check walked to `status` the way reviewers move it."""
        from apps.verification.constants import CaseStatus, CheckType
        from apps.verification.services.cases import locked_case, transition

        admin = self.persona("admin")
        path = {
            CaseStatus.NOT_STARTED: [],
            CaseStatus.SUBMITTED: [CaseStatus.SUBMITTED],
            CaseStatus.IN_REVIEW: [CaseStatus.SUBMITTED, CaseStatus.IN_REVIEW],
            CaseStatus.APPROVED: [CaseStatus.SUBMITTED, CaseStatus.IN_REVIEW, CaseStatus.APPROVED],
            CaseStatus.REJECTED: [CaseStatus.SUBMITTED, CaseStatus.IN_REVIEW, CaseStatus.REJECTED],
            CaseStatus.CHANGES_REQUESTED: [
                CaseStatus.SUBMITTED,
                CaseStatus.IN_REVIEW,
                CaseStatus.CHANGES_REQUESTED,
            ],
            CaseStatus.EXPIRED: [
                CaseStatus.SUBMITTED,
                CaseStatus.IN_REVIEW,
                CaseStatus.APPROVED,
                CaseStatus.EXPIRED,
            ],
        }[status]
        reasons = {
            CaseStatus.REJECTED: "The GST number doesn't match the business name.",
            CaseStatus.CHANGES_REQUESTED: "The PAN photo is blurred; upload it again.",
            CaseStatus.EXPIRED: "Past its validity.",
        }
        with transaction.atomic():
            case = locked_case(vendor, CheckType.BUSINESS)
            if case.status == status:  # a persona from an earlier batch
                self.report.add("verification_case", status)
                return case
            for step in path:
                if case.status == step:
                    continue
                actor = vendor if step == CaseStatus.SUBMITTED else admin
                case = transition(case, step, actor=actor, reason=reasons.get(step, ""))
        self.report.add("verification_case", status)
        return case

    # ---------- properties and gigs ----------

    def property_for(self, vendor: User, spec: dict):
        from apps.properties.models import Property

        prop = Property.objects.filter(vendor=vendor, name=spec["business_name"]).first()
        if prop:
            return prop
        return Property.objects.create(
            vendor=vendor,
            name=spec["business_name"],
            property_type=spec["property_type"],
            address=f"Seeded address, {spec['city']}",
            city=spec["city"],
            state=spec["state"],
            pincode=spec["pincode"],
            latitude=Decimal(str(spec["latitude"])),
            longitude=Decimal(str(spec["longitude"])),
            location_confirmed=True,
        )

    def gig(self, vendor: User, prop, *, title: str, status: str = "live", **fields):
        """A gig created, submitted and reviewed like a real one, then moved to `status`."""
        from apps.gigs.constants import Actor, GigStatus
        from apps.gigs.services import create_gig, transition

        data = {
            "property": prop,
            "title": f"{title} (seed {self.batch})",
            "description": "Seeded gig for acceptance testing: help with the day-to-day.",
            "role_template": "volunteer",
            "compensation_model": "volunteer",
            "start_date": days(30),
            "end_date": days(60),
            "apply_by": days(20),
            "slots": 2,
            "hours_per_day": 5,
            "days_per_week": 5,
            "stay_type": "dorm_bed",
            "meals": "two_meals",
            "wifi": True,
            **fields,
        }
        gig = create_gig(vendor, data)
        admin = self.persona("admin")
        steps = {
            GigStatus.DRAFT: [],
            GigStatus.IN_REVIEW: [(GigStatus.IN_REVIEW, Actor.VENDOR)],
            GigStatus.LIVE: [(GigStatus.IN_REVIEW, Actor.VENDOR), (GigStatus.LIVE, Actor.ADMIN)],
            GigStatus.PAUSED: [
                (GigStatus.IN_REVIEW, Actor.VENDOR),
                (GigStatus.LIVE, Actor.ADMIN),
                (GigStatus.PAUSED, Actor.VENDOR),
            ],
            GigStatus.CLOSED: [
                (GigStatus.IN_REVIEW, Actor.VENDOR),
                (GigStatus.LIVE, Actor.ADMIN),
                (GigStatus.CLOSED, Actor.VENDOR),
            ],
            GigStatus.ARCHIVED: [(GigStatus.ARCHIVED, Actor.VENDOR)],
        }[status]
        for to, actor in steps:
            user = admin if actor == Actor.ADMIN else vendor
            gig = transition(gig.pk, to, actor=actor, user=user, reason="Seeded.")
        return gig

    # ---------- applications, offers, bookings ----------

    def application(self, gig, talent: User):
        from apps.applications.services import apply

        return apply(
            talent,
            gig.pk,
            pitch="Three seasons at hostels in Himachal; happy at the front desk.",
            answers=[],
            proposed_start=gig.start_date + datetime.timedelta(days=1),
            proposed_end=gig.end_date - datetime.timedelta(days=1),
            attachments=[],
        )

    def offer(self, application):
        from apps.applications.models import Application
        from apps.offers.services import make_offer
        from apps.offers.terms import draft_for

        application = Application.objects.select_related("gig").get(pk=application.pk)
        return make_offer(
            application.pk,
            vendor=application.gig.vendor,
            terms=draft_for(application),
            message="We'd love to have you.",
        )

    def booking(self, gig, talent: User):
        """A confirmed booking: offered, accepted and signed by both."""
        from apps.agreements import services as agreements
        from apps.agreements.models import AgreementVersion, VersionStatus
        from apps.bookings.services import accept_offer

        application = self.application(gig, talent)
        self.offer(application)
        booking = accept_offer(application.pk, talent=talent)
        version = AgreementVersion.objects.get(
            agreement__booking=booking, status=VersionStatus.AWAITING
        )
        if not version.pdf_sha256:  # the render task may not have run yet: do it now
            agreements.render(version.pk)
        for signer in (booking.vendor, booking.talent):
            version.refresh_from_db()
            agreements.sign(
                version.pk, user=signer, consent=True, document_sha256=version.pdf_sha256
            )
        booking.refresh_from_db()
        return booking

    STAY_DAYS = 10

    def window(self, talent: User) -> dict:
        """Dates for a gig this talent will be booked on: after every stay they already
        have (bookings can't overlap), at least three weeks out (the rules want future
        dates; move_into_past shifts them back afterwards)."""
        from django.db.models import Max

        from apps.bookings.models import Booking

        latest = Booking.objects.filter(talent=talent).aggregate(end=Max("end_date"))["end"]
        start = max(days(20), (latest or today()) + datetime.timedelta(days=3))
        return {
            "start_date": start,
            "end_date": start + datetime.timedelta(days=self.STAY_DAYS),
            "apply_by": days(10),
        }

    def move_into_past(self, booking, started_days_ago: int) -> None:
        """Shift the stay so it started `started_days_ago` days ago (same length)."""
        from apps.bookings.models import Booking

        length = booking.end_date - booking.start_date
        start = today() - datetime.timedelta(days=started_days_ago)
        Booking.objects.filter(pk=booking.pk).update(start_date=start, end_date=start + length)
        booking.refresh_from_db()

    def fund(self, booking) -> None:
        """Escrow funded through the payment webhook, as Razorpay would confirm it."""
        import uuid

        from apps.money import escrow, webhooks
        from apps.money.gateway.fake import signed
        from apps.qa.providers import SEED_WEBHOOK_SECRET

        record, _ = escrow.start_funding(booking.pk, vendor=booking.vendor)
        body, headers = signed(
            {
                "event": "payment.captured",
                "payload": {
                    "payment": {
                        "entity": {
                            "id": f"seed_pay_{uuid.uuid4().hex[:12]}",
                            "order_id": record.gateway_order_id,
                            "status": "captured",
                            "amount": record.total_paise,
                            "fee": 0,
                            "tax": 0,
                        }
                    }
                },
            },
            SEED_WEBHOOK_SECRET,
            f"seed_evt_{uuid.uuid4().hex}",
        )
        webhooks.handle(body, headers)

    def payout_account(self, talent: User) -> None:
        from apps.money.models import PayoutAccount

        PayoutAccount.objects.get_or_create(
            talent=talent,
            defaults={
                "method": "upi",
                "display": "se•••@okseed",
                "provider_contact_id": f"seed_cont_{talent.pk.hex[:8]}",
                "fund_account_id": f"seed_fa_{talent.pk.hex[:12]}",
                "validation_status": "verified",
                "active": True,
                "pan_on_file": True,
                "verified_at": timezone.now() - datetime.timedelta(days=30),
            },
        )

    def check_in(self, booking, *, delivering: bool = True) -> None:
        from apps.bookings.lifecycle import Actor, BookingStatus
        from apps.bookings.services import transition

        at = timezone.make_aware(datetime.datetime.combine(booking.start_date, datetime.time(11)))
        transition(
            booking.pk, BookingStatus.CHECKED_IN, actor=Actor.VENDOR, user=booking.vendor, now=at
        )
        if delivering:
            transition(
                booking.pk,
                BookingStatus.DELIVERING,
                actor=Actor.TALENT,
                user=booking.talent,
                now=at,
            )

    def hand_in_all(self, booking, *, approve: bool | None):
        """Submit every deliverable; approve them (True), ask for changes (False) or leave
        them waiting (None)."""
        from apps.deliverables.models import Deliverable
        from apps.deliverables.services import review, submit

        for deliverable in Deliverable.objects.filter(booking=booking):
            submit(
                deliverable.pk,
                talent=booking.talent,
                post_url="https://www.instagram.com/p/seed-post/",
                file_ids=[],
                note="Posted with the paid-partnership label.",
                disclosure_confirmed=True,
            )
            if approve is not None:
                review(
                    deliverable.pk,
                    vendor=booking.vendor,
                    approve=approve,
                    note="Lovely." if approve else "Please tag the cafe in the first frame.",
                )

    # ---------- the whole seed ----------

    def run(self) -> SeedReport:
        from apps.qa.providers import seed_providers

        # All or nothing: a failed seed leaves no half-built batch behind.
        with seed_providers(), transaction.atomic():
            self._run()
        return self.report

    def _run(self) -> None:
        from apps.applications.constants import ApplicationStatus
        from apps.applications.services import transition as move_application
        from apps.applications.services import withdraw
        from apps.bookings.cancellation import cancel
        from apps.bookings.lifecycle import Actor, BookingStatus
        from apps.bookings.services import accept_offer
        from apps.bookings.services import transition as move_booking
        from apps.gigs.constants import GigStatus
        from apps.money import payouts
        from apps.offers.services import decline
        from apps.reviews.services import submit as review_stay
        from apps.verification.constants import CaseStatus

        self.persona("admin")
        hostel, cafe = self.persona("hostel_owner"), self.persona("cafe_owner")
        volunteer, creator = self.persona("volunteer"), self.persona("creator")
        trip_leader = self.persona("trip_leader")
        for vendor in (hostel, cafe):
            self.business_case(vendor, CaseStatus.APPROVED)
        for talent in (volunteer, creator, trip_leader):
            self.payout_account(talent)
        hostel_prop = self.property_for(hostel, self.personas["hostel_owner"])
        cafe_prop = self.property_for(cafe, self.personas["cafe_owner"])

        # Vendors in every verification state (approved: the personas above).
        for status in CaseStatus.values:
            if status != CaseStatus.APPROVED:
                vendor = self.extra_vendor(f"Seed vendor {status}", f"{status.title()} Inn")
                self.business_case(vendor, status)

        # Gigs in every status (filled comes from bookings below).
        for status in (
            GigStatus.DRAFT,
            GigStatus.IN_REVIEW,
            GigStatus.LIVE,
            GigStatus.PAUSED,
            GigStatus.CLOSED,
            GigStatus.ARCHIVED,
        ):
            self.gig(hostel, hostel_prop, title=f"Front desk ({status})", status=status)
            self.report.add("gig", status)

        # Applications in every status, on one live gig with plenty of places.
        open_gig = self.gig(hostel, hostel_prop, title="Hostel crew", slots=10)
        apps = {s: self.application(open_gig, self.extra_talent(f"Seed {s}")) for s in (
            "applied", "withdrawn", "shortlisted", "interview", "offered", "declined",
            "rejected", "expired",
        )}  # fmt: skip
        withdraw(apps["withdrawn"].pk, talent=apps["withdrawn"].talent, reason="Plans changed.")
        for key, path in {
            "shortlisted": [ApplicationStatus.SHORTLISTED],
            "interview": [ApplicationStatus.SHORTLISTED, ApplicationStatus.INTERVIEW],
            "rejected": [ApplicationStatus.REJECTED],
        }.items():
            for to in path:
                move_application(apps[key].pk, to, actor=Actor.VENDOR, user=hostel, reason="Seed")
        for key in ("offered", "declined", "expired"):
            self.offer(apps[key])
        offer = apps["declined"].offers.order_by("-created_at").first()
        decline(offer.pk, user=apps["declined"].talent, reason="Found a gig closer to home.")
        apps["expired"].refresh_from_db()
        move_application(  # as the expire_offers job does, once the deadline passes
            apps["expired"].pk,
            ApplicationStatus.EXPIRED,
            actor=Actor.SYSTEM,
            reason="No reply within 48 hours.",
            now=apps["expired"].offer_expires_at + datetime.timedelta(minutes=1),
        )
        for status in apps:
            self.report.add("application", status)
        # "confirmed" applications come with every booking below.

        # Bookings at every stage. Volunteer gigs at the hostel, paid creator gigs at the
        # cafe (escrow), a trip leader on a hybrid gig.
        def volunteer_gig(title, talent):
            return self.gig(hostel, hostel_prop, title=title, slots=1, **self.window(talent))

        def paid_gig(title, talent):
            return self.gig(
                cafe,
                cafe_prop,
                title=title,
                slots=1,
                **self.window(talent),
                role_template="content_creator",
                compensation_model="hybrid",
                stipend_amount=Decimal("5000"),
                stipend_period="total",
                deliverables=[{"type": "instagram_reel", "quantity": 1}],
            )

        person = self.extra_talent("Seed signing")

        signing = self.application(volunteer_gig("Signing", person), person)
        self.offer(signing)
        accept_offer(signing.pk, talent=signing.talent)
        self.report.add("booking", BookingStatus.SIGNING)

        self.booking(volunteer_gig("Confirmed", volunteer), volunteer)  # fills its gig (1 slot)
        self.report.add("booking", BookingStatus.CONFIRMED)
        self.report.add("gig", GigStatus.FILLED)

        checked_in = self.booking(volunteer_gig("Checked in", trip_leader), trip_leader)
        self.move_into_past(checked_in, 1)
        self.check_in(checked_in, delivering=False)
        self.report.add("booking", BookingStatus.CHECKED_IN)

        # Paid: delivering, deliverable waiting for review.
        delivering = self.booking(paid_gig("Reel, waiting for review", creator), creator)
        self.fund(delivering)
        self.move_into_past(delivering, 3)
        self.check_in(delivering)
        self.hand_in_all(delivering, approve=None)
        self.report.add("booking", BookingStatus.DELIVERING)
        self.report.add("escrow", "held")

        # Paid: changes asked.
        person = self.extra_talent("Seed changes")
        changes = self.booking(paid_gig("Reel, changes asked", person), person)
        self.fund(changes)
        self.move_into_past(changes, 4)
        self.check_in(changes)
        self.hand_in_all(changes, approve=False)
        self.report.add("deliverable", "changes_requested")

        # Paid: approved, released, paid out, completed and reviewed by both.
        done = self.booking(paid_gig("Reel, done and reviewed", creator), creator)
        self.fund(done)
        self.move_into_past(done, 20)  # a 10-day stay that ended ten days ago
        self.check_in(done)
        self.hand_in_all(done, approve=True)  # approving releases the escrow
        payouts.pay(done.escrow.pk)
        move_booking(done.pk, BookingStatus.COMPLETED, actor=Actor.SYSTEM, reason="Stay ended.")
        scores = {"communication": 5, "accuracy": 5, "safety": 5, "reliability": 5}
        review_stay(
            done.pk,
            author=cafe,
            rating=5,
            text="Brilliant reels, delivered on time and exactly as agreed. Would host again.",
            **scores,
        )
        review_stay(
            done.pk,
            author=creator,
            rating=5,
            text="Lovely cafe and kind hosts. Clear brief, calm room, and paid on time.",
            **scores,
        )
        self.report.add("booking", BookingStatus.REVIEWED)
        self.report.add("escrow", "released")
        self.report.add("review", "both_sides")

        # Volunteer stay finished, reviews still open.
        finished = self.booking(volunteer_gig("Finished, reviews open", volunteer), volunteer)
        self.move_into_past(finished, 25)
        self.check_in(finished)
        move_booking(
            finished.pk, BookingStatus.COMPLETED, actor=Actor.VENDOR, user=hostel, reason="Done."
        )
        self.report.add("booking", BookingStatus.COMPLETED)

        # Cancelled late by the host (inside the cancellation window).
        person = self.extra_talent("Seed late")
        late = self.booking(paid_gig("Cancelled late", person), person)
        self.fund(late)
        cancel(
            late.pk,
            user=cafe,
            by=Actor.VENDOR,
            reason="emergency",
            note="Flooding near the cafe; closed for the week.",
        )
        self.report.add("booking", BookingStatus.CANCELLED)

        # No-show.
        person = self.extra_talent("Seed no-show")
        no_show = self.booking(volunteer_gig("No-show", person), person)
        self.move_into_past(no_show, 2)
        move_booking(
            no_show.pk,
            BookingStatus.NO_SHOW,
            actor=Actor.VENDOR,
            user=hostel,
            reason="Didn't arrive.",
        )
        self.report.add("booking", BookingStatus.NO_SHOW)

        # Disputed: escrow frozen for a finance decision. (The dispute case with its
        # evidence comes with the trust and safety work.)
        person = self.extra_talent("Seed dispute")
        disputed = self.booking(paid_gig("Disputed", person), person)
        self.fund(disputed)
        self.move_into_past(disputed, 5)
        self.check_in(disputed)
        move_booking(
            disputed.pk,
            BookingStatus.DISPUTED,
            actor=Actor.TALENT,
            user=disputed.talent,
            reason="The host asked for work outside the agreement.",
        )
        self.report.add("booking", BookingStatus.DISPUTED)
