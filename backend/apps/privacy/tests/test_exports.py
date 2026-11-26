import json
from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.common.models import AuditLog
from apps.media.storage import get_storage
from apps.privacy.models import DataExport, ExportStatus
from apps.privacy.services import exports
from apps.privacy.tests.helpers import busy_talent
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def test_the_export_holds_their_data_and_no_secrets():
    booking, talent, _ = busy_talent()
    data = json.loads(exports.render(talent))
    assert data["format_version"] == 1
    assert data["account"]["phone"] == talent.phone
    assert data["talent_profile"][0]["display_name"] == talent.talent_profile.display_name
    assert data["talent_profile"][0]["skills"]
    assert {c["purpose"] for c in data["consents"]} == {"terms", "privacy", "location"}
    assert [m["body"] for m in data["messages_sent"]] == ["See you on the 3rd!"]
    assert data["bookings_as_talent"][0]["id"] == str(booking.pk)
    assert data["signatures"] and data["applications"]
    assert data["push_devices"] and "token" not in data["push_devices"][0]
    assert data["activity_log"]  # what they did, from the audit log
    text = json.dumps(data)
    for secret in ("password", "object_key", "code_secret", "idempotency_key", "pdf_key"):
        assert f'"{secret}"' not in text
    # The host's side of the booking isn't in the talent's export.
    assert data["bookings_as_host"] == [] and data["vendor_profile"] == []


def test_reviews_about_you_are_only_published_ones():
    booking, talent, _ = busy_talent()
    from apps.reviews.models import Review

    fields = {
        "booking": booking,
        "author": booking.vendor,
        "subject": talent,
        "rating": 5,
        "text": "Lovely to host.",
        "communication": 5,
        "accuracy": 5,
        "safety": 5,
        "reliability": 5,
    }
    Review.objects.create(**fields, subject_side="talent", status="submitted")
    data = exports.collect(talent)
    assert data["reviews_about_you"] == []


def test_export_api_gives_a_short_lived_link(settings):
    _, talent, _ = busy_talent()
    client = client_for(talent)
    created = client.post(reverse("privacy:exports"))
    assert created.status_code == 201
    export = DataExport.objects.get(pk=created.json()["id"])
    assert export.status == ExportStatus.READY
    body, content_type = get_storage().objects[export.object_key]
    assert content_type == "application/json" and json.loads(body)["account"]["id"]

    link = client.post(reverse("privacy:export-link", args=[export.pk]))
    assert link.status_code == 200
    assert link.json()["expires_in_seconds"] == settings.PRIVACY_EXPORT_URL_SECONDS
    assert "X-Goog-Expires=300" in link.json()["url"] and "download=1" in link.json()["url"]
    assert AuditLog.objects.filter(action="privacy.export_link", object_id=str(export.pk)).exists()

    listed = client.get(reverse("privacy:exports")).json()
    assert [e["id"] for e in listed["results"]] == [str(export.pk)]


def test_someone_elses_export_is_not_found():
    _, talent, _ = busy_talent()
    export = exports.create(talent)
    other = client_for(busy_talent()[1])
    assert other.post(reverse("privacy:export-link", args=[export.pk])).status_code == 404


def test_exports_expire_and_their_files_go(settings):
    _, talent, _ = busy_talent()
    export = exports.create(talent)
    later = timezone.now() + timedelta(hours=settings.PRIVACY_EXPORT_KEEP_HOURS, minutes=1)
    assert exports.expire_due(later) == 1
    export.refresh_from_db()
    assert export.status == ExportStatus.EXPIRED
    assert export.object_key not in get_storage().objects
    response = client_for(talent).post(reverse("privacy:export-link", args=[export.pk]))
    assert response.status_code == 410


def test_a_few_exports_a_day(settings):
    settings.PRIVACY_EXPORTS_PER_DAY = 1
    _, talent, _ = busy_talent()
    client = client_for(talent)
    assert client.post(reverse("privacy:exports")).status_code == 201
    second = client.post(reverse("privacy:exports"))
    assert second.status_code == 429 and second.json()["code"] == "export_limit"
