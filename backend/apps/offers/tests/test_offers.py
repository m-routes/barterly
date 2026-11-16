from datetime import timedelta
from decimal import Decimal

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.agreements.models import AgreementVersion, VersionStatus
from apps.applications.constants import ApplicationStatus as A
from apps.applications.services import apply, withdraw
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.bookings import jobs
from apps.bookings.models import Booking
from apps.common.models import AuditLog
from apps.gigs.constants import CompensationModel
from apps.gigs.tests.factories import in_days
from apps.notifications.models import Notification
from apps.offers import services
from apps.offers.models import Offer, OfferStatus, Party
from apps.offers.terms import COUNTERABLE, digest, draft_for, validate
from apps.offers.tests.helpers import make_offer_for
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def hybrid_gig(**kwargs):
    return live_gig(
        compensation_model=CompensationModel.HYBRID,
        stipend_amount=Decimal("5000"),
        stipend_period="per_month",
        deliverables=[{"type": "instagram_reel", "quantity": 2}],
        **kwargs,
    )


def applied(gig=None, talent=None):
    gig = gig or hybrid_gig()
    return apply(
        talent or eligible_talent(), gig.pk, pitch="Hi", answers=[], attachments=[], **dates()
    )


class TestTerms:
    def test_draft_takes_the_gigs_terms_and_the_applicants_dates(self):
        application = applied()
        terms = draft_for(application)
        assert terms["start_date"] == str(application.proposed_start)
        assert terms["stipend_amount"] == "5000.00" and terms["stipend_period"] == "per_month"
        assert terms["deliverables"] == [{"type": "instagram_reel", "quantity": 2, "notes": ""}]
        assert terms["usage_rights"]["scope"] == "organic"
        assert validate(terms, compensation_model="hybrid") == terms

    def test_equal_terms_hash_equally_whatever_their_types(self):
        terms = draft_for(applied())
        same = {**terms, "stipend_amount": Decimal("5000"), "hours_per_day": "4"}
        assert digest(terms) == digest({**same, "hours_per_day": terms["hours_per_day"]})

    @pytest.mark.parametrize(
        ("change", "field"),
        [
            ({"hours_per_day": 7}, "hours_per_day"),
            ({"days_per_week": 7}, "days_per_week"),
            ({"stipend_amount": None}, "stipend_amount"),
            ({"deliverables": []}, "deliverables"),
            ({"usage_rights": None}, "usage_rights"),
            ({"end_date": str(in_days(31))}, "end_date"),
            ({"start_date": str(in_days(-1))}, "start_date"),
            ({"cancellation_policy": "never"}, "cancellation_policy"),
        ],
    )
    def test_rules(self, change, field):
        terms = {**draft_for(applied()), **change}
        with pytest.raises(ValidationError) as caught:
            validate(terms, compensation_model="hybrid")
        assert field in caught.value.detail

    def test_volunteer_gigs_have_no_stipend_or_content(self):
        terms = draft_for(applied(live_gig()))
        assert terms["stipend_amount"] is None and terms["usage_rights"] is None
        with pytest.raises(ValidationError, match="stipend"):
            validate({**terms, "stipend_amount": "100"}, compensation_model="volunteer")


class TestMakingAnOffer:
    def test_freezes_the_terms_and_tells_the_talent(self):
        application = applied()
        offer = make_offer_for(application, message="Welcome aboard", hours_per_day=4)
        application.refresh_from_db()
        assert application.status == A.OFFERED
        assert application.offer_expires_at == offer.created_at + timedelta(hours=48)
        assert offer.revision == 1 and offer.proposed_by == Party.VENDOR
        assert offer.terms["hours_per_day"] == 4 and offer.terms_sha256 == digest(offer.terms)
        assert Notification.objects.filter(
            user=application.talent, kind="application.offered"
        ).exists()
        log = AuditLog.objects.get(action="offer.sent")
        assert log.after["terms_sha256"] == offer.terms_sha256

    def test_terms_cant_change_in_the_database(self):
        offer = make_offer_for(applied())
        with pytest.raises(DatabaseError, match="frozen"), transaction.atomic():
            Offer.objects.filter(pk=offer.pk).update(terms={})
        with pytest.raises(DatabaseError, match="kept"), transaction.atomic():
            Offer.objects.filter(pk=offer.pk).delete()

    def test_only_the_gigs_vendor_and_only_once(self):
        application = applied()
        with pytest.raises(services.Application.DoesNotExist):
            services.make_offer(
                application.pk, vendor=hybrid_gig().vendor, terms=draft_for(application)
            )
        make_offer_for(application)
        with pytest.raises(services.OfferError, match="already has an offer"):
            make_offer_for(application)

    def test_the_status_endpoint_no_longer_offers(self):
        application = applied()
        response = client_for(application.gig.vendor).post(
            f"/api/v1/applications/{application.pk}/status/", {"status": "offered"}, format="json"
        )
        assert response.status_code == 400


class TestAnswering:
    def test_accepting_books_the_offers_dates_and_draws_up_the_agreement(self):
        application = applied()
        offer = make_offer_for(application, start_date=str(in_days(35)))
        booking = services.accept(offer.pk, user=application.talent)
        offer.refresh_from_db()
        assert offer.status == OfferStatus.ACCEPTED
        assert booking.start_date == in_days(35)  # the offer's dates, not the application's
        version = AgreementVersion.objects.get(agreement__booking=booking)
        assert version.number == 1 and version.status == VersionStatus.AWAITING
        assert version.terms == offer.terms and version.offer_id == offer.pk
        assert version.rendered  # drawn up right after the booking committed

    def test_declining_ends_the_application(self):
        application = applied()
        offer = make_offer_for(application)
        services.decline(offer.pk, user=application.talent, reason="Found another stay")
        offer.refresh_from_db()
        application.refresh_from_db()
        assert offer.status == OfferStatus.DECLINED and application.status == A.DECLINED
        assert Notification.objects.filter(
            user=application.gig.vendor, kind="application.declined"
        ).exists()

    def test_you_cant_answer_your_own_offer(self):
        application = applied()
        offer = make_offer_for(application)
        with pytest.raises(services.OfferError, match="waiting for the other side"):
            services.accept(offer.pk, user=application.gig.vendor)
        with pytest.raises(Offer.DoesNotExist):
            services.accept(offer.pk, user=eligible_talent())

    def test_withdrawing_lapses_the_open_offer(self):
        application = applied()
        offer = make_offer_for(application)
        withdraw(application.pk, talent=application.talent)
        offer.refresh_from_db()
        assert offer.status == OfferStatus.LAPSED and "withdrawn" in offer.status_reason
        assert AuditLog.objects.filter(action="offer.lapsed").exists()


class TestCounter:
    def test_the_talent_may_change_only_some_terms(self):
        application = applied()
        offer = make_offer_for(application)
        with pytest.raises(services.OfferError, match="can't change stay_type"):
            services.counter(offer.pk, talent=application.talent, changes={"stay_type": "tent"})
        with pytest.raises(services.OfferError, match="at least one"):
            services.counter(offer.pk, talent=application.talent, changes={})
        with pytest.raises(ValidationError):
            services.counter(offer.pk, talent=application.talent, changes={"hours_per_day": 9})
        assert set(COUNTERABLE) == {
            "start_date",
            "end_date",
            "hours_per_day",
            "days_per_week",
            "stipend_amount",
            "deliverables",
            "usage_rights",
        }

    def test_a_counter_gives_the_vendor_time_and_tells_them(self):
        application = applied()
        offer = make_offer_for(application)
        later = timezone.now() + timedelta(hours=40)
        counter = services.counter(
            offer.pk,
            talent=application.talent,
            changes={"stipend_amount": "7000", "hours_per_day": 3},
            message="A little more, please",
            now=later,
        )
        offer.refresh_from_db()
        application.refresh_from_db()
        assert offer.status == OfferStatus.COUNTERED
        assert counter.proposed_by == Party.TALENT and counter.final and counter.counter_of == offer
        assert counter.terms["stipend_amount"] == "7000.00"
        assert application.offer_expires_at == later + timedelta(hours=48)
        note = Notification.objects.get(user=application.gig.vendor, kind="offer.countered")
        assert note.payload["changed"] == ["hours_per_day", "stipend_amount"]

    def test_the_vendor_accepting_the_counter_books_it(self):
        application = applied()
        offer = make_offer_for(application)
        counter = services.counter(
            offer.pk, talent=application.talent, changes={"start_date": str(in_days(40))}
        )
        with pytest.raises(services.OfferError, match="waiting for the other side"):
            services.accept(counter.pk, user=application.talent)
        booking = services.accept(counter.pk, user=application.gig.vendor)
        assert booking.start_date == in_days(40)
        assert Notification.objects.filter(
            user=application.talent, kind="application.confirmed"
        ).exists()

    def test_declining_the_counter_sends_the_original_back_as_final(self):
        application = applied()
        offer = make_offer_for(application)
        counter = services.counter(
            offer.pk, talent=application.talent, changes={"stipend_amount": "9000"}
        )
        final = services.decline(counter.pk, user=application.gig.vendor, reason="Budget is fixed")
        assert final.terms == offer.terms and final.final and final.revision == 3
        assert Notification.objects.filter(
            user=application.talent, kind="offer.counter_declined"
        ).exists()
        with pytest.raises(services.OfferError, match="already asked for a change"):
            services.counter(final.pk, talent=application.talent, changes={"hours_per_day": 2})
        booking = services.accept(final.pk, user=application.talent)
        assert booking.agreement.versions.get().terms["stipend_amount"] == "5000.00"

    def test_an_unanswered_counter_expires_the_application(self):
        application = applied()
        offer = make_offer_for(application)
        counter = services.counter(
            offer.pk, talent=application.talent, changes={"hours_per_day": 3}
        )
        jobs.expire_offers(timezone.now() + timedelta(hours=49))
        counter.refresh_from_db()
        application.refresh_from_db()
        assert application.status == A.EXPIRED and counter.status == OfferStatus.LAPSED


class TestApi:
    def test_offer_counter_and_accept(self):
        application = applied()
        vendor, talent = client_for(application.gig.vendor), client_for(application.talent)
        draft = vendor.get(f"/api/v1/applications/{application.pk}/offer-draft/").json()
        bad = vendor.post(
            f"/api/v1/applications/{application.pk}/offer/",
            {"terms": {**draft, "hours_per_day": 8}},
            format="json",
        )
        assert bad.status_code == 400 and "hours_per_day" in str(bad.json())
        made = vendor.post(
            f"/api/v1/applications/{application.pk}/offer/",
            {"terms": draft, "message": "Join us"},
            format="json",
        )
        assert made.status_code == 201, made.json()
        assert made.json()["your_turn"] is False

        thread = talent.get(f"/api/v1/applications/{application.pk}/offers/").json()
        assert thread["your_turn"] and thread["can_counter"]
        offer_id = thread["open_offer"]
        countered = talent.post(
            f"/api/v1/offers/{offer_id}/counter/",
            {"changes": {"days_per_week": 4}, "message": "Four days?"},
            format="json",
        )
        assert countered.status_code == 201, countered.json()
        body = countered.json()
        assert body["offers"][-1]["changed_fields"] == ["days_per_week"]
        assert body["your_turn"] is False and body["can_counter"] is False

        accepted = vendor.post(f"/api/v1/offers/{body['open_offer']}/accept/")
        assert accepted.status_code == 201, accepted.json()
        booking = Booking.objects.get(pk=accepted.json()["booking"])
        assert (
            booking.agreement.versions.get().pk
            == AgreementVersion.objects.get(pk=accepted.json()["agreement_version"]).pk
        )

    def test_strangers_see_nothing(self):
        application = applied()
        make_offer_for(application)
        stranger = client_for(eligible_talent())
        assert stranger.get(f"/api/v1/applications/{application.pk}/offers/").status_code == 404
        offer = Offer.objects.get(application=application)
        assert stranger.post(f"/api/v1/offers/{offer.pk}/accept/").status_code == 404

    def test_legacy_accept_and_decline_act_on_the_open_offer(self):
        application = applied()
        talent = client_for(application.talent)
        refused = talent.post(f"/api/v1/applications/{application.pk}/accept/")
        assert refused.status_code == 409
        make_offer_for(application)
        declined = talent.post(f"/api/v1/applications/{application.pk}/decline/", {}, format="json")
        assert declined.status_code == 200 and declined.json()["status"] == "declined"
        assert Offer.objects.get(application=application).status == OfferStatus.DECLINED
