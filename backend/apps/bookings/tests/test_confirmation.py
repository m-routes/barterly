"""Confirmation side effects: both sign → confirmed, slot taken, others held or expired,
details unlocked. Cancellation before check-in: reasons, policy effect, slot released,
the place offered on."""

from datetime import datetime, time, timedelta

import pytest
from django.utils import timezone

from apps.agreements.services import AgreementError
from apps.agreements.tests.helpers import sign_both
from apps.applications import services as applications
from apps.applications.constants import ApplicationStatus as A
from apps.applications.models import Application
from apps.applications.services import apply
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.bookings import cancellation, jobs
from apps.bookings.lifecycle import Actor
from apps.bookings.lifecycle import BookingStatus as B
from apps.bookings.models import Booking, Cancellation, CancellationEffect
from apps.bookings.services import accept_offer
from apps.bookings.tests.helpers import accepted, booked, offered
from apps.common.models import AuditLog
from apps.gigs.constants import GigStatus
from apps.notifications.models import Notification
from apps.offers import services as offers
from apps.offers.models import Offer, OfferStatus
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def kinds_for(user) -> set[str]:
    return set(Notification.objects.filter(user=user).values_list("kind", flat=True))


def shortlisted(gig, fit: int, **apply_overrides):
    application = apply(
        eligible_talent(),
        gig.pk,
        pitch="Happy to step in.",
        answers=[],
        attachments=[],
        **{**dates(), **apply_overrides},
    )
    applications.transition(application.pk, A.SHORTLISTED, actor=Actor.VENDOR, user=gig.vendor)
    Application.objects.filter(pk=application.pk).update(fit_score=fit)
    return application


def at(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


# ---------- Both sign ----------


class TestWhenBothSign:
    def test_details_unlock_only_once_both_have_signed(self):
        booking = accepted()
        prop = booking.gig.property
        prop.directions = "Past the blue gate, second lane on the left."
        prop.save(update_fields=["directions"])
        talent, vendor = client_for(booking.talent), client_for(booking.vendor)
        url = f"/api/v1/bookings/{booking.pk}/details/"
        locked = talent.get(url)
        assert locked.status_code == 409 and "both sides have signed" in locked.json()["message"]

        sign_both(booking)

        mine = talent.get(url).json()
        assert mine["host"]["phone"] == booking.vendor.phone
        assert mine["talent"]["phone"] == booking.talent.phone
        assert mine["place"]["address"] == prop.address
        assert mine["place"]["directions"] == "Past the blue gate, second lane on the left."
        if prop.latitude is not None:
            assert mine["place"]["maps_url"].startswith("https://www.google.com/maps/dir/")
        host_view = vendor.get(url).json()
        assert host_view["talent"]["phone"] == booking.talent.phone
        assert host_view["place"] is None  # the host knows their own address
        assert client_for(eligible_talent()).get(url).status_code == 404

    def test_the_exact_location_in_the_gig_api_carries_directions(self):
        booking = booked()
        prop = booking.gig.property
        prop.directions = "Ask for Ravi at the cafe."
        prop.save(update_fields=["directions"])
        body = client_for(booking.talent).get(f"/api/v1/properties/{prop.pk}/public/").json()
        assert body["exact_location"]["directions"] == "Ask for Ravi at the cafe."

    def test_a_later_version_signed_doesnt_confirm_again(self):
        from apps.agreements import services as agreements

        booking = booked()
        events_before = booking.events.count()
        agreements.propose_change(
            booking.pk, user=booking.vendor, changes={"hours_per_day": 3}, reason="Quieter month"
        )
        sign_both(booking)
        booking.refresh_from_db()
        assert booking.status == B.CONFIRMED
        assert booking.events.count() == events_before


class TestWhenTheGigFills:
    def test_hold_puts_other_offers_on_hold_and_unsigned_bookings_wait(self, settings):
        settings.BOOKING_WHEN_FULL = "hold"
        gig = live_gig(slots=1)
        first = accepted(gig)
        pending = offered(gig)
        signing = accepted(gig)

        sign_both(first)

        held = Offer.objects.get(application=pending)
        assert held.status == OfferStatus.HELD
        pending.refresh_from_db()
        assert pending.status == A.OFFERED
        start = held.terms["start_date"]
        assert pending.offer_expires_at == timezone.make_aware(
            datetime.combine(datetime.fromisoformat(start).date(), time.min)
        )
        assert "offer.held" in kinds_for(pending.talent)
        with pytest.raises(offers.OfferError, match="on hold"):
            offers.accept(held.pk, user=pending.talent)
        signing.refresh_from_db()
        assert signing.status == B.SIGNING
        assert "booking.waiting_for_place" in kinds_for(signing.talent)
        with pytest.raises(AgreementError, match="Every place"):
            sign_both(signing)
        gig.refresh_from_db()
        assert gig.status == GigStatus.FILLED
        entry = AuditLog.objects.get(action="gig.full_settled")
        assert entry.after == {
            "rule": "hold",
            "booking_id": str(first.pk),
            "held": 1,
            "expired": 0,
            "waiting": 1,
            "cancelled": 0,
        }

    def test_expire_lapses_other_offers_and_calls_off_unsigned_bookings(self, settings):
        settings.BOOKING_WHEN_FULL = "expire"
        gig = live_gig(slots=1)
        first = accepted(gig)
        pending = offered(gig)
        signing = accepted(gig)

        sign_both(first)

        pending.refresh_from_db()
        assert pending.status == A.EXPIRED
        assert Offer.objects.get(application=pending).status == OfferStatus.LAPSED
        signing.refresh_from_db()
        assert signing.status == B.CANCELLED
        record = signing.cancellation
        assert (record.by, record.reason, record.effect) == ("system", "slots_filled", "none")

    def test_nothing_happens_to_others_while_slots_remain(self):
        gig = live_gig(slots=2)
        first = accepted(gig)
        pending = offered(gig)
        sign_both(first)
        assert Offer.objects.get(application=pending).status == OfferStatus.OPEN
        gig.refresh_from_db()
        assert gig.status == GigStatus.LIVE

    def test_an_unknown_rule_is_refused(self, settings):
        settings.BOOKING_WHEN_FULL = "shrug"
        gig = live_gig(slots=1)
        booking = accepted(gig)
        with pytest.raises(ValueError, match="BOOKING_WHEN_FULL"):
            sign_both(booking)


# ---------- Cancelling ----------


class TestPolicyEffect:
    @pytest.mark.parametrize(
        ("policy", "days_before", "expected"),
        [
            ("flexible", 3, "free"),
            ("flexible", 2, "late"),
            ("moderate", 7, "free"),
            ("moderate", 6, "late"),
            ("strict", 14, "free"),
            ("strict", 13, "late"),
            ("strict", 1, "last_minute"),
            ("moderate", 0, "last_minute"),
            ("moderate", -1, "last_minute"),
        ],
    )
    def test_confirmed_bookings_by_either_side(self, policy, days_before, expected):
        today = timezone.localdate()
        for by in ("talent", "vendor"):
            effect = cancellation.effect_for(
                by=by,
                was_status=B.CONFIRMED,
                policy=policy,
                start=today + timedelta(days=days_before),
                today=today,
            )
            assert effect.effect == expected
            assert effect.days_before_start == days_before

    def test_no_effect_before_confirmation_or_when_barterly_cancels(self):
        today = timezone.localdate()
        start = today + timedelta(days=1)
        assert (
            cancellation.effect_for(
                by="talent", was_status=B.SIGNING, policy="strict", start=start, today=today
            ).effect
            == "none"
        )
        for by in ("system", "admin"):
            assert (
                cancellation.effect_for(
                    by=by, was_status=B.CONFIRMED, policy="strict", start=start, today=today
                ).effect
                == "none"
            )


class TestCancelling:
    def test_preview_lists_my_reasons_and_the_effect(self):
        booking = booked()
        talent = client_for(booking.talent)
        body = talent.get(f"/api/v1/bookings/{booking.pk}/cancel/").json()
        assert [r["code"] for r in body["reasons"]][:2] == ["illness", "emergency"]
        assert "property_unavailable" not in {r["code"] for r in body["reasons"]}
        assert (body["effect"], body["policy"], body["notice_days"]) == ("free", "moderate", 7)
        host = client_for(booking.vendor).get(f"/api/v1/bookings/{booking.pk}/cancel/").json()
        assert "property_unavailable" in {r["code"] for r in host["reasons"]}

    def test_a_reason_from_the_list_is_required(self):
        booking = booked()
        talent = client_for(booking.talent)
        url = f"/api/v1/bookings/{booking.pk}/cancel/"
        assert talent.post(url, {}, format="json").status_code == 400
        wrong_side = talent.post(url, {"reason": "staffing"}, format="json")
        assert wrong_side.status_code == 400
        no_note = talent.post(url, {"reason": "other"}, format="json")
        assert no_note.status_code == 400 and "Say a little" in str(no_note.json())
        ok = talent.post(url, {"reason": "other", "note": "Visa delayed"}, format="json")
        assert ok.status_code == 200, ok.json()
        body = ok.json()
        assert body["status"] == "cancelled"
        assert body["cancellation"]["reason"] == "other"
        assert body["cancellation"]["note"] == "Visa delayed"
        again = talent.post(url, {"reason": "illness"}, format="json")
        assert again.status_code == 409

    def test_late_cancellation_by_the_host_is_recorded_against_the_host(self):
        booking = booked()
        three_days_before = at(booking.start_date - timedelta(days=3))
        cancellation.cancel(
            booking.pk,
            user=booking.vendor,
            by="vendor",
            reason="staffing",
            now=three_days_before,
        )
        record = Cancellation.objects.get(booking=booking)
        assert (record.by, record.effect, record.policy, record.notice_days) == (
            "vendor",
            CancellationEffect.LATE,
            "moderate",
            7,
        )
        assert record.days_before_start == 3
        event = booking.events.last()
        assert event.metadata["reason_code"] == "staffing" and event.metadata["effect"] == "late"
        assert AuditLog.objects.filter(action="booking.cancelled", object_id=str(booking.pk))

    def test_after_check_in_it_cant_be_cancelled_here(self):
        from apps.bookings.services import transition

        booking = booked()
        transition(
            booking.pk,
            B.CHECKED_IN,
            actor=Actor.VENDOR,
            user=booking.vendor,
            now=at(booking.start_date),
        )
        with pytest.raises(cancellation.CancellationRefused, match="hasn't checked in"):
            cancellation.cancel(booking.pk, user=booking.talent, by="talent", reason="illness")

    def test_cancelling_before_both_signed_has_no_effect_and_frees_nothing(self):
        gig = live_gig(slots=1)
        booking = accepted(gig)
        cancellation.cancel(booking.pk, user=booking.talent, by="talent", reason="plans_changed")
        assert Cancellation.objects.get(booking=booking).effect == "none"
        assert not Notification.objects.filter(kind="booking.place_opened").exists()

    def test_admins_cancel_through_the_transition_endpoint_with_a_note(self):
        from apps.accounts.tests.factories import AdminUserFactory

        booking = booked()
        admin = client_for(AdminUserFactory(roles=["ops"]))
        response = admin.post(
            f"/api/v1/bookings/{booking.pk}/transition/",
            {"status": "cancelled", "reason": "Fraud check"},
            format="json",
        )
        assert response.status_code == 200, response.json()
        record = Cancellation.objects.get(booking=booking)
        assert (record.by, record.reason, record.note, record.effect) == (
            "admin",
            "admin",
            "Fraud check",
            "none",
        )


class TestThePlaceIsOfferedOn:
    def test_held_offers_open_again_first(self):
        gig = live_gig(slots=1)
        waiting = offered(gig)
        shortlisted(gig, fit=90)
        booking = booked(gig)  # fills the gig: the other offer goes on hold
        assert Offer.objects.get(application=waiting).status == OfferStatus.HELD
        now = timezone.now()

        cancellation.cancel(booking.pk, user=booking.talent, by="talent", reason="illness", now=now)

        offer = Offer.objects.get(application=waiting)
        assert offer.status == OfferStatus.OPEN
        waiting.refresh_from_db()
        assert waiting.offer_expires_at == now + timedelta(hours=48)
        assert "offer.reopened" in kinds_for(waiting.talent)
        assert not Offer.objects.filter(step_in_for=booking).exists()  # someone's in line
        gig.refresh_from_db()
        assert gig.status == GigStatus.LIVE
        assert "booking.place_opened" in kinds_for(gig.vendor)
        assert "booking.place_opened" not in kinds_for(booking.talent)

    def test_the_next_shortlisted_applicant_is_offered_the_same_terms(self):
        gig = live_gig(slots=1)
        second = shortlisted(gig, fit=60)
        best = shortlisted(gig, fit=80)
        booking = booked(gig)

        cancellation.cancel(booking.pk, user=booking.vendor, by="vendor", reason="staffing")

        offer = Offer.objects.get(step_in_for=booking)
        assert offer.application_id == best.pk
        assert offer.terms == booking.agreement.current_version.terms
        assert offer.proposed_by == "vendor" and offer.created_by_id == gig.vendor_id
        best.refresh_from_db()
        assert best.status == A.OFFERED and best.offer_expires_at
        second.refresh_from_db()
        assert second.status == A.SHORTLISTED
        assert "application.offered" in kinds_for(best.talent)
        assert "offer.step_in" in kinds_for(gig.vendor)
        entry = AuditLog.objects.get(action="offer.sent", object_id=str(offer.pk))
        assert entry.actor is None and entry.after["step_in_for"] == str(booking.pk)

        # Accepting it is an ordinary booking that both must sign.
        stepped_in = accept_offer(best.pk, talent=best.talent)
        assert stepped_in.status == B.SIGNING
        sign_both(stepped_in)
        stepped_in.refresh_from_db()
        assert stepped_in.status == B.CONFIRMED

    def test_applicants_already_booked_on_those_dates_are_skipped(self):
        gig = live_gig(slots=1)
        free = shortlisted(gig, fit=50)
        taken = shortlisted(gig, fit=90)
        booked(talent=taken.talent)  # a booking elsewhere on the same dates
        booking = booked(gig)

        cancellation.cancel(booking.pk, user=booking.talent, by="talent", reason="illness")

        assert Offer.objects.get(step_in_for=booking).application_id == free.pk

    def test_no_step_in_when_turned_off_or_nobody_is_shortlisted(self, settings):
        gig = live_gig(slots=1)
        booking = booked(gig)
        cancellation.cancel(booking.pk, user=booking.talent, by="talent", reason="illness")
        assert not Offer.objects.filter(step_in_for=booking).exists()
        assert "booking.place_opened" in kinds_for(gig.vendor)

        settings.STEP_IN_OFFERS = False
        other_gig = live_gig(slots=1)
        shortlisted(other_gig, fit=70)
        other = booked(other_gig)
        cancellation.cancel(other.pk, user=other.talent, by="talent", reason="illness")
        assert not Offer.objects.filter(step_in_for=other).exists()

    def test_no_step_in_once_the_stay_has_started(self):
        gig = live_gig(slots=1)
        shortlisted(gig, fit=70)
        booking = booked(gig)
        cancellation.cancel(
            booking.pk,
            user=booking.talent,
            by="talent",
            reason="illness",
            now=at(booking.start_date + timedelta(days=1)),
        )
        assert not Offer.objects.filter(step_in_for=booking).exists()


class TestJobs:
    def test_unsigned_bookings_are_called_off_when_the_stay_starts(self):
        booking = accepted()
        assert (
            jobs.expire_offers(at(booking.start_date - timedelta(days=1)))["unsigned_cancelled"]
            == 0
        )
        result = jobs.expire_offers(at(booking.start_date))
        assert result["unsigned_cancelled"] == 1
        booking.refresh_from_db()
        assert booking.status == B.CANCELLED
        assert (booking.cancellation.reason, booking.cancellation.effect) == ("not_signed", "none")

    def test_held_offers_lapse_when_the_stay_would_have_started(self, settings):
        settings.BOOKING_WHEN_FULL = "hold"
        gig = live_gig(slots=1)
        first = accepted(gig)
        waiting = offered(gig)
        sign_both(first)
        start = Booking.objects.get(pk=first.pk).start_date
        jobs.expire_offers(at(start - timedelta(days=1)))
        waiting.refresh_from_db()
        assert waiting.status == A.OFFERED
        jobs.expire_offers(at(start))
        waiting.refresh_from_db()
        assert waiting.status == A.EXPIRED
        assert waiting.status_reason == "No place opened up before the stay."
        assert Offer.objects.get(application=waiting).status == OfferStatus.LAPSED
