import pytest
from django.urls import reverse

from apps.accounts.tests.factories import TalentFactory
from apps.common.models import AuditLog
from apps.privacy.models import ConsentRecord
from apps.privacy.services import consents
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db
URL = reverse("privacy:consents")
V = "2026-11-draft-1"


def by_purpose(body):
    return {row["purpose"]: row for row in body}


def test_nothing_is_assumed():
    user = TalentFactory()
    states = {s.purpose: s for s in consents.states(user)}
    assert set(states) == {"terms", "privacy", "location", "social", "marketing"}
    assert not any(s.granted for s in states.values())
    assert states["terms"].required and not states["marketing"].required
    assert consents.needs_required_consent(user)


def test_giving_and_withdrawing_are_the_same_call_and_each_is_audited():
    user = TalentFactory()
    client = client_for(user)
    given = client.post(URL, {"purpose": "location", "granted": True, "version": V}, format="json")
    assert given.status_code == 200
    assert by_purpose(given.json())["location"]["granted"] is True
    assert consents.has_consent(user, "location")

    withdrawn = client.post(URL, {"purpose": "location", "granted": False}, format="json")
    assert withdrawn.status_code == 200
    assert by_purpose(withdrawn.json())["location"]["granted"] is False
    assert not consents.has_consent(user, "location")
    assert consents.withdrawn(user, "location")

    rows = list(ConsentRecord.objects.filter(user=user).order_by("id"))
    assert [(r.granted, r.version) for r in rows] == [(True, V), (False, V)]
    actions = list(
        AuditLog.objects.filter(actor=user).order_by("id").values_list("action", flat=True)
    )
    assert actions == ["privacy.consent_given", "privacy.consent_withdrawn"]
    last = AuditLog.objects.filter(actor=user).order_by("id").last()
    assert last.before == {"purpose": "location", "granted": True, "version": V}
    assert last.after["granted"] is False


def test_each_purpose_is_separate():
    user = TalentFactory()
    consents.record(user, "marketing", granted=True, version=V)
    assert consents.has_consent(user, "marketing")
    assert not consents.has_consent(user, "social")
    assert not consents.has_consent(user, "location")


def test_a_stale_version_is_refused():
    client = client_for(TalentFactory())
    response = client.post(
        URL, {"purpose": "social", "granted": True, "version": "2025-old"}, format="json"
    )
    assert response.status_code == 409
    assert response.json()["code"] == "document_changed"


def test_giving_needs_a_version():
    client = client_for(TalentFactory())
    response = client.post(URL, {"purpose": "social", "granted": True}, format="json")
    assert response.status_code == 400
    assert "version" in response.json()["details"]


def test_required_consents_are_withdrawn_by_deleting_the_account():
    client = client_for(TalentFactory())
    response = client.post(URL, {"purpose": "terms", "granted": False}, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "consent_required"


def test_a_new_document_version_asks_again(settings):
    user = TalentFactory()
    consents.record_sign_up(user, terms_version=V, privacy_version=V, source="web")
    assert not consents.needs_required_consent(user)
    settings.PRIVACY_DOCUMENT_VERSIONS = {**settings.PRIVACY_DOCUMENT_VERSIONS, "privacy": "v2"}
    assert consents.needs_required_consent(user)
    privacy = by_purpose(client_for(user).get(URL).json())["privacy"]
    assert privacy["needs_renewal"] is True and privacy["current_version"] == "v2"


def test_records_are_append_only():
    record = consents.record(TalentFactory(), "marketing", granted=True, version=V)
    with pytest.raises(TypeError):
        record.save()
    with pytest.raises(TypeError):
        ConsentRecord.objects.filter(pk=record.pk).update(granted=False)


def test_history_and_the_signed_out_case(client):
    user = TalentFactory()
    consents.record(user, "marketing", granted=True, version=V)
    consents.record(user, "marketing", granted=False)
    history = client_for(user).get(reverse("privacy:consent-history")).json()
    assert [r["granted"] for r in history["results"]] == [False, True]
    assert client.get(URL).status_code == 401


def test_public_documents_and_grievance_officer(client):
    docs = client.get(reverse("privacy:documents")).json()
    assert {d["purpose"]: d["version"] for d in docs}["terms"] == V
    officer = client.get(reverse("privacy:grievance")).json()
    assert officer["email"] and officer["resolve_days"] == 15
