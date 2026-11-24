"""The seed makes every state it promises, through the real services."""

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.accounts.models import User
from apps.qa.journeys import ARCHIVE_PREFIX, reset_onboarding_persona
from apps.qa.seed import Seeder, SeedRefused, load_personas

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _seedable(settings, django_capture_on_commit_callbacks):
    # The seed swaps in its own stand-ins for signing and payments. Commit callbacks
    # (notifications, follow-up events) run as they would on staging.
    settings.ALLOW_SEED = True
    with django_capture_on_commit_callbacks(execute=True):
        yield


def test_seed_covers_every_state():
    from apps.applications.constants import ApplicationStatus
    from apps.applications.models import Application
    from apps.bookings.lifecycle import BookingStatus
    from apps.bookings.models import Booking
    from apps.gigs.constants import GigStatus
    from apps.gigs.models import Gig
    from apps.money.models import Escrow
    from apps.reviews.models import Review
    from apps.verification.constants import CaseStatus, CheckType
    from apps.verification.models import VerificationCase

    report = Seeder(batch=1).run()

    assert set(Gig.objects.values_list("status", flat=True)) == set(GigStatus.values)
    assert set(Application.objects.values_list("status", flat=True)) == set(
        ApplicationStatus.values
    )
    booking_states = set(Booking.objects.values_list("status", flat=True))
    for status in (
        BookingStatus.SIGNING,
        BookingStatus.CONFIRMED,
        BookingStatus.CHECKED_IN,
        BookingStatus.DELIVERING,
        BookingStatus.COMPLETED,
        BookingStatus.REVIEWED,
        BookingStatus.CANCELLED,
        BookingStatus.NO_SHOW,
        BookingStatus.DISPUTED,
    ):
        assert status in booking_states, status
    cases = VerificationCase.objects.filter(check_type=CheckType.BUSINESS)
    assert set(cases.values_list("status", flat=True)) == set(CaseStatus.values)
    assert Escrow.objects.filter(status="released").exists()
    assert Escrow.objects.filter(status="held").exists()
    assert Review.objects.count() >= 2
    assert report.personas["hostel_owner"] == load_personas()["hostel_owner"]["phone"]


def test_history_reads_naturally():
    """Stays that have started are in the past, not next month."""
    from django.utils import timezone

    from apps.bookings.lifecycle import BookingStatus
    from apps.bookings.models import Booking

    Seeder(batch=2).run()
    today = timezone.localdate()
    for booking in Booking.objects.filter(
        status__in=[BookingStatus.CHECKED_IN, BookingStatus.DELIVERING, BookingStatus.COMPLETED]
    ):
        assert booking.start_date <= today, booking.status


def test_runs_again_as_a_new_batch():
    Seeder(batch=3).run()
    Seeder(batch=4).run()  # personas reused, extra people new
    personas = load_personas()
    for spec in personas.values():
        assert User.objects.filter(phone=spec["phone"]).count() <= 1


def test_refused_where_switched_off(settings):
    settings.ALLOW_SEED = False
    with pytest.raises(SeedRefused):
        Seeder()
    with pytest.raises(CommandError):
        call_command("seed_staging")


def test_production_settings_never_allow_it():
    from pathlib import Path

    text = (Path(__file__).resolve().parents[3] / "config/settings/production.py").read_text()
    assert "ALLOW_SEED = False" in text


def test_seeded_signatures_and_payments_are_labelled():
    from apps.agreements.models import Signature
    from apps.money.models import Escrow

    Seeder(batch=5).run()
    assert set(Signature.objects.values_list("provider", flat=True)) == {"staging_seed"}
    assert all(
        e.gateway_payment_id.startswith("seed_pay_")
        for e in Escrow.objects.exclude(gateway_payment_id="")
    )


def test_reset_onboarding_retires_the_old_account():
    personas = load_personas()
    phone = personas["onboarding_vendor"]["phone"]
    old = User.objects.create_user(phone, role="vendor")
    retired = reset_onboarding_persona(personas)
    assert retired.pk == old.pk
    old.refresh_from_db()
    assert old.phone.startswith(ARCHIVE_PREFIX) and not old.is_active
    assert not User.objects.filter(phone=phone).exists()


def test_prepare_journey_gives_the_talent_every_starting_point():
    from apps.applications.models import Application
    from apps.bookings.models import Booking

    out = StringIO()
    call_command("prepare_journey", "--talent", "volunteer", stdout=out)
    ids = json.loads(out.getvalue())
    assert Application.objects.get(pk=ids["offer_application"]).status == "offered"
    assert Booking.objects.get(pk=ids["booking_arriving_today"]).status == "confirmed"
    assert Booking.objects.get(pk=ids["booking_deliverable_due"]).status == "delivering"
    assert Booking.objects.get(pk=ids["booking_to_review"]).status == "completed"
    from apps.money.models import Escrow

    unfunded = Booking.objects.get(pk=ids["booking_unfunded"])
    assert unfunded.status == "confirmed"
    assert not Escrow.objects.filter(booking=unfunded, status="held").exists()
    tomorrow = Booking.objects.get(pk=ids["booking_starts_tomorrow"])
    assert tomorrow.status == "confirmed"
    assert (tomorrow.start_date - timezone.localdate()).days == 1
    with pytest.raises(CommandError):
        call_command("prepare_journey", "--talent", "hostel_owner")


def test_reset_journeys_gives_a_fresh_host_and_a_free_verified_talent():
    from apps.bookings.models import Booking
    from apps.qa.journeys import reset_journey_personas
    from apps.verification.constants import BadgeKind
    from apps.verification.services.cases import active_badge_kinds

    personas = load_personas()
    seeder = Seeder(personas=personas)
    old_talent = seeder.persona("journey_creator")
    reset_journey_personas(personas)

    new_talent = User.objects.get(phone=personas["journey_creator"]["phone"])
    assert new_talent.pk != old_talent.pk
    assert BadgeKind.ID_VERIFIED in active_badge_kinds(new_talent)
    assert not Booking.objects.filter(talent=new_talent).exists()
    assert not User.objects.filter(phone=personas["onboarding_vendor"]["phone"]).exists()
