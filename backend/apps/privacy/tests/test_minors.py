from datetime import date

import pytest
from django.core import mail
from django.urls import reverse

from apps.accounts.tests.factories import AdminUserFactory
from apps.applications.models import Application
from apps.bookings.tests.helpers import offered
from apps.common.models import AuditLog
from apps.privacy.models import MinorCase, MinorStatus
from apps.privacy.services import minors
from apps.profiles.models import TalentProfile
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def test_an_under_18_birth_date_on_the_profile_suspends_and_tells_the_trust_team(
    settings, django_capture_on_commit_callbacks
):
    settings.TRUST_TEAM_EMAILS = ["trust@barterly.test"]
    application = offered()
    talent = application.talent
    with django_capture_on_commit_callbacks(execute=True):
        response = client_for(talent).patch(
            reverse("profiles:talent-me"), {"date_of_birth": "2012-05-01"}, format="json"
        )
    assert response.status_code == 403
    assert response.json()["code"] == "underage"

    case = MinorCase.objects.get(user=talent)
    assert case.status == MinorStatus.OPEN and case.source == "profile_dob"
    talent.refresh_from_db()
    assert not talent.is_active  # without apps.safety: deactivated
    assert case.restriction == "accounts.deactivated"
    assert not TalentProfile.objects.filter(user=talent).exists()  # hidden
    application.refresh_from_db()
    assert application.status == "withdrawn"
    assert AuditLog.objects.filter(action="privacy.minor_flagged", object_id=str(case.pk))
    assert len(mail.outbox) == 1
    assert str(case.pk) in mail.outbox[0].body and talent.phone not in mail.outbox[0].body
    # The birth date itself was never saved.
    assert TalentProfile.all_objects.get(user=talent).date_of_birth != date(2012, 5, 1)


def test_flagging_twice_keeps_one_open_case():
    talent = offered().talent
    first = minors.flag(talent, source="staff")
    assert minors.flag(talent, source="report") == first


def test_confirming_purges_their_data():
    talent = offered().talent
    case = minors.flag(talent, source="report")
    staff = AdminUserFactory()
    minors.confirm(case.pk, actor=staff)
    case.refresh_from_db()
    talent.refresh_from_db()
    assert case.status == MinorStatus.CONFIRMED and case.decided_by == staff
    assert talent.phone.startswith("del-")
    assert Application.objects.get(talent=talent).pitch == ""
    assert AuditLog.objects.filter(action="privacy.minor_confirmed", actor=staff).exists()
    with pytest.raises(minors.MinorCaseError):
        minors.confirm(case.pk, actor=staff)


def test_clearing_lifts_the_suspension():
    talent = offered().talent
    case = minors.flag(talent, source="profile_dob")
    with pytest.raises(minors.MinorCaseError):
        minors.clear(case.pk, actor=AdminUserFactory(), note="  ")
    minors.clear(case.pk, actor=AdminUserFactory(), note="Typo; Aadhaar shows 1998.")
    talent.refresh_from_db()
    assert talent.is_active
    assert TalentProfile.objects.filter(user=talent).exists()
    assert MinorCase.objects.get(pk=case.pk).status == MinorStatus.CLEARED


def test_an_adult_birth_date_is_fine():
    talent = offered().talent
    response = client_for(talent).patch(
        reverse("profiles:talent-me"), {"date_of_birth": "1995-05-01"}, format="json"
    )
    assert response.status_code == 200
    assert not MinorCase.objects.exists()
