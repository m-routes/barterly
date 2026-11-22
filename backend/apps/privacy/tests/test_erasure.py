from datetime import timedelta

import pytest
from django.db import IntegrityError, InternalError, ProgrammingError, connection, transaction
from django.urls import reverse
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import User
from apps.agreements.models import AgreementVersion, Signature
from apps.applications.tests.helpers import dates
from apps.bookings.tests.helpers import booked
from apps.chat.models import Message
from apps.common.models import AuditLog
from apps.money.models import LedgerEntry
from apps.notifications.models import PushDevice
from apps.privacy.models import ConsentRecord, DeletionRequest, DeletionStatus
from apps.privacy.services import erasure
from apps.privacy.tests.helpers import busy_talent
from apps.profiles.models import TalentProfile
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db
URL = reverse("privacy:deletion")


def test_anonymise_replaces_personal_fields_and_keeps_records():
    booking, talent, now = busy_talent()
    phone = talent.phone
    RefreshToken.for_user(talent)
    signatures_before = Signature.objects.filter(user=talent).count()
    hash_before = Signature.objects.get(user=talent).document_sha256
    with transaction.atomic(), connection.cursor() as cursor:
        # Give the fake signature the evidence a real one has.
        cursor.execute("SELECT set_config('barterly.erasure', 'on', true)")
        Signature.objects.filter(user=talent).update(
            ip="203.0.113.9",
            user_agent="Mozilla/5.0",
            device="Pixel 8",
            phone=phone,
            evidence={"otp_provider": "firebase", "otp_uid": "uid-123"},
        )

    summary = erasure.anonymise(talent, now=now)

    talent.refresh_from_db()
    assert talent.phone.startswith("del-") and len(talent.phone) <= 16
    assert talent.email is None and not talent.is_active and not talent.has_usable_password()
    profile = TalentProfile.all_objects.get(user=talent)
    assert profile.display_name == "Deleted member" and profile.deleted_at is not None
    assert (profile.emergency_contact_phone, profile.date_of_birth, profile.bio) == ("", None, "")
    assert not profile.skills.exists()
    assert not PushDevice.objects.filter(user=talent).exists()
    message = Message.objects.get(sender=talent)
    assert "deleted their account" in message.body

    # Agreements kept: the signature row stays, its document hash unchanged, the signer's
    # phone masked to the last four, the IP and device gone.
    signature = Signature.objects.get(user=talent)
    assert Signature.objects.filter(user=talent).count() == signatures_before
    assert signature.document_sha256 == hash_before
    assert signature.phone == f"******{phone[-4:]}"
    assert signature.ip is None and signature.user_agent == "" and signature.device == ""
    assert signature.evidence == {"otp_provider": "firebase"}
    assert AgreementVersion.objects.filter(agreement__booking=booking).exists()

    # Consent proof is kept (it names no one once the user row is anonymous).
    assert ConsentRecord.objects.filter(user=talent).count() == 3
    # Audit entries kept, personal values erased.
    sign_up = AuditLog.objects.filter(object_id=str(talent.pk), after__has_key="phone")
    assert all(e.after["phone"] == "[erased]" for e in sign_up)
    assert not AuditLog.objects.filter(after__phone=phone).exists()
    assert AuditLog.objects.filter(action="privacy.account_anonymised", object_id=str(talent.pk))
    # Sessions end.
    assert BlacklistedToken.objects.filter(token__user=talent).exists()
    assert summary["user"] == 1 and summary["agreements"] == 1


def test_anonymise_is_idempotent():
    _, talent, now = busy_talent()
    erasure.anonymise(talent, now=now)
    erasure.anonymise(talent, now=now)
    talent.refresh_from_db()
    assert talent.phone.startswith("del-")


def test_the_same_phone_can_sign_up_again_as_a_new_account():
    _, talent, now = busy_talent()
    phone, old_id = talent.phone, talent.pk
    erasure.anonymise(talent, now=now)
    fresh = User.objects.create_user(phone)
    assert fresh.pk != old_id


def test_signatures_stay_frozen_outside_erasure():
    booking = booked()
    signature = Signature.objects.filter(user=booking.talent).first()
    with pytest.raises((InternalError, IntegrityError, ProgrammingError)), transaction.atomic():
        Signature.objects.filter(pk=signature.pk).update(ip=None)
    with pytest.raises((InternalError, IntegrityError, ProgrammingError)), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('barterly.erasure', 'on', true)")
        # Even with the flag, the signed document can't change.
        Signature.objects.filter(pk=signature.pk).update(document_sha256="0" * 64)


def test_the_ledger_is_untouched():
    from apps.money.tests.helpers import funded, paid_booking

    booking = paid_booking()
    funded(booking)
    before = list(LedgerEntry.objects.values_list("pk", "amount_paise"))
    talent = booking.talent
    erasure.anonymise(talent)
    assert list(LedgerEntry.objects.values_list("pk", "amount_paise")) == before


def test_deletion_is_blocked_by_an_active_booking():
    booking = booked()
    response = client_for(booking.talent).post(URL, {"confirm": True}, format="json")
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "deletion_blocked"
    assert [b["code"] for b in body["details"]["blockers"]] == ["active_bookings"]
    assert client_for(booking.talent).get(URL).json()["blockers"][0]["count"] == 1


def test_request_cancel_and_run_after_the_grace_period(settings):
    _, talent, _ = busy_talent()
    client = client_for(talent)
    assert client.post(URL, {"confirm": False}, format="json").status_code == 400

    scheduled = client.post(URL, {"confirm": True, "reason": "Moving on"}, format="json")
    assert scheduled.status_code == 202
    assert scheduled.json()["request"]["status"] == "scheduled"
    assert client.post(URL, {"confirm": True}, format="json").status_code == 202  # same one
    assert DeletionRequest.objects.filter(user=talent).count() == 1

    cancelled = client.delete(URL)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "cancelled"
    assert client.delete(URL).status_code == 404

    client.post(URL, {"confirm": True}, format="json")
    assert erasure.run_due(timezone.now()) == {"anonymised": 0, "postponed": 0}
    later = timezone.now() + timedelta(days=settings.PRIVACY_DELETION_GRACE_DAYS, minutes=1)
    assert erasure.run_due(later) == {"anonymised": 1, "postponed": 0}
    entry = DeletionRequest.objects.get(user=talent, status=DeletionStatus.COMPLETED)
    assert entry.summary["user"] == 1
    talent.refresh_from_db()
    assert not talent.is_active
    actions = set(AuditLog.objects.filter(object_id=str(entry.pk)).values_list("action", flat=True))
    assert {"privacy.deletion_requested", "privacy.deletion_completed"} <= actions


def test_a_booking_made_during_the_grace_period_postpones_deletion(settings):
    _, talent, _ = busy_talent()
    erasure.request_deletion(talent)
    booked(talent=talent, **dates(52, 58))
    later = timezone.now() + timedelta(days=settings.PRIVACY_DELETION_GRACE_DAYS, minutes=1)
    assert erasure.run_due(later) == {"anonymised": 0, "postponed": 1}
    talent.refresh_from_db()
    assert talent.is_active


def test_registered_anonymisers_run_too():
    _, talent, now = busy_talent()
    seen = []
    erasure.register_anonymiser("test_step", lambda user, now: seen.append(user.pk) or 1)
    try:
        summary = erasure.anonymise(talent, now=now)
    finally:
        erasure._anonymisers[:] = [a for a in erasure._anonymisers if a[0] != "test_step"]
    assert seen == [talent.pk] and summary["test_step"] == 1
