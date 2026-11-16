import hashlib
from datetime import timedelta

import pytest
from django.db import DatabaseError, transaction
from django.utils import timezone

from apps.accounts.tests.fakes import token_for
from apps.agreements import pdf, services
from apps.agreements.esign.base import get_provider
from apps.agreements.models import AgreementVersion, Signature, VersionStatus
from apps.agreements.tests.helpers import awaiting, sign, sign_both
from apps.bookings.lifecycle import Actor
from apps.bookings.lifecycle import BookingStatus as B
from apps.bookings.services import BookingRefused, transition
from apps.common.models import AuditLog
from apps.gigs.tests.factories import in_days
from apps.media.storage import get_storage
from apps.notifications.models import Notification
from apps.offers import services as offers
from apps.offers.tests.helpers import make_offer_for
from apps.offers.tests.test_offers import applied
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def booking(**offer_changes):
    application = applied()
    offer = make_offer_for(application, **offer_changes)
    return offers.accept(offer.pk, user=application.talent)


def on_day_one(b):
    return timezone.make_aware(
        timezone.datetime.combine(b.start_date, timezone.datetime.min.time())
    )


class TestDrawingUp:
    def test_version_one_is_stored_with_its_hash(self):
        b = booking()
        version = awaiting(b)
        data, content_type = get_storage().objects[version.pdf_key]
        assert content_type == "application/pdf"
        assert version.pdf_sha256 == hashlib.sha256(data).hexdigest()
        assert version.pdf_size == len(data)
        assert version.template == pdf.CURRENT_TEMPLATE
        assert version.template_sha256 == pdf.template_sha256(pdf.CURRENT_TEMPLATE)
        assert AuditLog.objects.filter(action="agreement.rendered").count() == 1
        assert services.render(version.pk).pdf_sha256 == version.pdf_sha256  # idempotent
        notified = set(
            Notification.objects.filter(kind="agreement.ready").values_list("user_id", flat=True)
        )
        assert notified == {b.talent_id, b.vendor_id}

    def test_the_text_has_every_required_clause_and_the_placeholder_warning(self):
        version = awaiting(booking(hours_per_day=4, days_per_week=5))
        html = pdf.render_html(version)
        assert "PLACEHOLDER LEGAL TEXT" in html and "NOT REVIEWED BY A LAWYER" in html
        assert "no more than 20 hours in any week" in html  # the hour cap
        assert "Content and usage rights" in html and "non-exclusive" in html
        assert "Safety and conduct" in html and "call 112" in html
        assert "up to 7 days before the arrival date" in html  # moderate policy
        assert "INR 5,000.00 per month" in html
        assert not pdf.TEMPLATES[pdf.CURRENT_TEMPLATE].reviewed

    def test_a_failed_render_doesnt_undo_the_booking_and_the_job_retries(self):
        from apps.agreements.pdf import get_renderer

        get_renderer().fail = True
        b = booking()
        version = awaiting(b)
        assert b.pk and not version.rendered
        with pytest.raises(services.AgreementError, match="still being prepared"):
            sign(version, b.vendor)
        get_renderer().fail = False
        assert services.render_pending() == {"rendered": 1, "failed": 0}
        version.refresh_from_db()
        assert version.rendered


class TestSigning:
    def test_in_force_only_once_both_have_signed(self):
        b = booking()
        version = awaiting(b)
        sign(version, b.vendor)
        b.agreement.refresh_from_db()
        assert not b.agreement.in_force
        assert Notification.objects.filter(user=b.talent, kind="agreement.signed").exists()
        b.refresh_from_db()
        assert b.status == B.SIGNING  # not confirmed until both have signed
        with pytest.raises(BookingRefused, match="signing to checked_in"):
            transition(b.pk, B.CHECKED_IN, actor=Actor.VENDOR, user=b.vendor, now=on_day_one(b))

        sign(version, b.talent)
        version.refresh_from_db()
        b.agreement.refresh_from_db()
        assert version.status == VersionStatus.ACTIVE and version.in_force_at
        assert b.agreement.current_version == version
        assert {s.party for s in version.signatures.all()} == {"talent", "vendor"}
        assert AuditLog.objects.filter(action="agreement.signed").count() == 2
        assert AuditLog.objects.filter(action="agreement.in_force").exists()
        transition(b.pk, B.CHECKED_IN, actor=Actor.VENDOR, user=b.vendor, now=on_day_one(b))

    def test_refusals(self):
        b = booking()
        version = awaiting(b)
        with pytest.raises(services.AgreementError, match="isn't the document on file"):
            sign(version, b.vendor, document_sha256="0" * 64)
        with pytest.raises(services.AgreementError, match="Tick the box"):
            sign(version, b.vendor, consent=False)
        sign(version, b.vendor)
        with pytest.raises(services.AgreementError, match="already signed"):
            sign(version, b.vendor)
        with pytest.raises(AgreementVersion.DoesNotExist):
            sign(version, applied().talent)
        transition(b.pk, B.CANCELLED, actor=Actor.TALENT, user=b.talent, reason="Ill")
        with pytest.raises(services.AgreementError, match="booking is cancelled"):
            sign(version, b.talent)

    def test_signatures_and_versions_cant_be_rewritten(self):
        b = booking()
        version = sign_both(b)
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            Signature.objects.filter(version=version).update(ip="10.0.0.1")
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            Signature.objects.filter(version=version).delete()
        with pytest.raises(DatabaseError, match="frozen"), transaction.atomic():
            AgreementVersion.objects.filter(pk=version.pk).update(terms={})
        with pytest.raises(DatabaseError, match="fixed once drawn up"), transaction.atomic():
            AgreementVersion.objects.filter(pk=version.pk).update(pdf_sha256="f" * 64)


class TestInAppProvider:
    @pytest.fixture(autouse=True)
    def _in_app(self, settings):
        from apps.agreements.esign import base

        settings.ESIGN_PROVIDER = "apps.agreements.esign.inapp.InAppESignProvider"
        base._build.cache_clear()

    def test_challenge_asks_for_an_otp(self):
        b = booking()
        version = awaiting(b)
        challenge = services.challenge(version.pk, user=b.talent)
        assert challenge.method == "otp" and challenge.max_age_seconds == 300
        assert challenge.phone_hint.endswith(b.talent.phone[-4:]) and "•" in challenge.phone_hint
        assert "version 1" in challenge.consent_text
        assert version.pdf_sha256[:16] in challenge.consent_text

    def test_needs_a_fresh_otp_for_the_signers_own_phone(self):
        b = booking()
        version = awaiting(b)
        with pytest.raises(services.AgreementError, match="one-time code"):
            sign(version, b.talent)
        with pytest.raises(services.AgreementError, match="phone number on your Barterly"):
            sign(version, b.talent, otp_token=token_for(b.vendor.phone))
        stale = timezone.now() - timedelta(minutes=6)
        with pytest.raises(services.AgreementError, match="last 5 minutes"):
            sign(version, b.talent, otp_token=token_for(b.talent.phone, at=stale))
        with pytest.raises(services.AgreementError, match="didn't work"):
            sign(version, b.talent, otp_token="garbage")

    def test_records_otp_time_ip_and_device(self):
        b = booking()
        version = awaiting(b)
        talent = client_for(b.talent)
        challenge = talent.get(f"/api/v1/agreement-versions/{version.pk}/sign/").json()
        response = talent.post(
            f"/api/v1/agreement-versions/{version.pk}/sign/",
            {
                "consent": True,
                "document_sha256": challenge["document_sha256"],
                "otp_token": token_for(b.talent.phone),
            },
            format="json",
            HTTP_USER_AGENT="BarterlyApp/1.4 (Android 15)",
            HTTP_X_CLIENT_DEVICE="Pixel 9",
            HTTP_X_FORWARDED_FOR="203.0.113.7",
        )
        assert response.status_code == 200, response.json()
        signature = Signature.objects.get(version=version)
        assert signature.provider == "in_app_otp" and signature.phone == b.talent.phone
        assert signature.otp_verified_at and signature.ip == "203.0.113.7"
        assert signature.device == "Pixel 9" and signature.user_agent.startswith("BarterlyApp")
        assert signature.consent_text == challenge["consent_text"]
        mine = response.json()["versions"][0]
        assert mine["signed_by_me"] and not mine["can_sign"]
        assert mine["signatures"][0]["otp_confirmed"] is True


class TestChanges:
    def test_a_change_is_a_new_version_both_sign_again(self):
        b = booking()
        v1 = sign_both(b)
        v2 = services.propose_change(
            b.pk,
            user=b.vendor,
            changes={"end_date": str(in_days(45)), "hours_per_day": 3},
            reason="We close early this season",
        )
        b.agreement.refresh_from_db()
        assert v2.number == 2 and v2.status == VersionStatus.AWAITING and v2.rendered
        assert v2.changed_fields == ["end_date", "hours_per_day"]
        assert b.agreement.current_version == v1  # still in force until both sign v2
        assert Notification.objects.filter(user=b.talent, kind="agreement.change_proposed").exists()

        sign(v2, b.vendor)
        sign(v2, b.talent)
        v1.refresh_from_db()
        v2.refresh_from_db()
        b.refresh_from_db()
        assert v1.status == VersionStatus.SUPERSEDED and v2.status == VersionStatus.ACTIVE
        assert b.end_date == in_days(45)
        log = AuditLog.objects.get(action="booking.dates_changed")
        assert log.after["agreement_version"] == 2

    def test_rules_for_changes(self):
        b = booking()
        sign_both(b)
        with pytest.raises(services.AgreementError, match="Say why"):
            services.propose_change(b.pk, user=b.talent, changes={"hours_per_day": 3}, reason="")
        with pytest.raises(services.AgreementError, match="can't be changed: compensation_model"):
            services.propose_change(
                b.pk, user=b.talent, changes={"compensation_model": "paid"}, reason="x"
            )
        with pytest.raises(services.AgreementError, match="at least one"):
            services.propose_change(b.pk, user=b.talent, changes={}, reason="x")
        transition(b.pk, B.CHECKED_IN, actor=Actor.VENDOR, user=b.vendor, now=on_day_one(b))
        with pytest.raises(services.AgreementError, match="dates can't change"):
            services.propose_change(
                b.pk, user=b.talent, changes={"end_date": str(in_days(49))}, reason="x"
            )
        # Other terms can still change after check-in.
        version = services.propose_change(
            b.pk, user=b.talent, changes={"hours_per_day": 2}, reason="Tired"
        )
        assert version.number == 2

    def test_a_newer_change_voids_the_pending_one_and_changes_can_be_declined(self):
        b = booking()
        sign_both(b)
        v2 = services.propose_change(b.pk, user=b.vendor, changes={"hours_per_day": 3}, reason="a")
        v3 = services.propose_change(b.pk, user=b.vendor, changes={"hours_per_day": 2}, reason="b")
        v2.refresh_from_db()
        assert v2.status == VersionStatus.VOIDED and v3.number == 3
        services.decline_change(v3.pk, user=b.talent, reason="Too few hours for the reels")
        v3.refresh_from_db()
        b.agreement.refresh_from_db()
        assert v3.status == VersionStatus.DECLINED and b.agreement.current_version.number == 1
        assert Notification.objects.filter(user=b.vendor, kind="agreement.change_declined").exists()

    def test_version_one_cant_be_declined(self):
        b = booking()
        with pytest.raises(services.AgreementError, match="first version can't be declined"):
            services.decline_change(awaiting(b).pk, user=b.talent)


class TestApi:
    def test_list_detail_pdf_and_changes(self):
        b = booking()
        vendor = client_for(b.vendor)
        listed = vendor.get("/api/v1/agreements/").json()["results"]
        assert listed[0]["awaiting_my_signature"] and listed[0]["awaiting_version"] == 1
        detail = vendor.get(f"/api/v1/bookings/{b.pk}/agreement/").json()
        assert detail["my_side"] == "vendor" and not detail["in_force"]
        version = detail["versions"][0]
        assert version["can_sign"] and version["template_reviewed"] is False
        link = vendor.get(f"/api/v1/agreement-versions/{version['id']}/pdf/").json()
        assert link["sha256"] == version["pdf_sha256"] and link["url"].startswith("https://")

        sign_both(b)
        changed = vendor.post(
            f"/api/v1/bookings/{b.pk}/agreement/changes/",
            {"changes": {"meals": "all_meals"}, "reason": "Kitchen reopened"},
            format="json",
        )
        assert changed.status_code == 201, changed.json()
        assert changed.json()["versions"][0]["proposed_by"] == "vendor"
        declined = client_for(b.talent).post(
            f"/api/v1/agreement-versions/{changed.json()['versions'][0]['id']}/decline/",
            {"reason": "No thanks"},
            format="json",
        )
        assert declined.status_code == 200
        assert declined.json()["versions"][0]["status"] == "declined"

    def test_strangers_see_nothing(self):
        b = booking()
        stranger = client_for(applied().talent)
        version = awaiting(b)
        assert stranger.get(f"/api/v1/bookings/{b.pk}/agreement/").status_code == 404
        assert stranger.get(f"/api/v1/agreement-versions/{version.pk}/pdf/").status_code == 404
        assert stranger.get("/api/v1/agreements/").json()["results"] == []
        response = stranger.post(
            f"/api/v1/bookings/{b.pk}/agreement/changes/",
            {"changes": {"meals": "none"}, "reason": "x"},
            format="json",
        )
        assert response.status_code == 404
        assert get_provider().signed == []


def test_the_talents_trips_link_to_the_agreement():
    b = booking()
    trips = client_for(b.talent).get("/api/v1/applications/mine/").json()["results"]
    assert trips[0]["agreement"] == str(b.agreement.pk)
