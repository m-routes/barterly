import hashlib
import io

import pytest
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.common.models import AuditLog
from apps.media.models import MediaFile, MediaStatus, ScanStatus
from apps.media.policy import MB
from apps.media.storage import get_storage

pytestmark = pytest.mark.django_db

UPLOAD_URL = reverse("media:upload-url")
CONFIRM = reverse("media:confirm")


def png_bytes(size=(1600, 900), color=(200, 80, 40)) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format="PNG")
    return out.getvalue()


PDF = b"%PDF-1.7\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 64


@pytest.fixture
def user():
    return TalentFactory()


@pytest.fixture
def api(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


def request_upload(api, data: bytes, content_type: str, kind: str, **extra):
    body = {"kind": kind, "content_type": content_type, "size_bytes": len(data), **extra}
    return api.post(UPLOAD_URL, body, format="json")


def upload(api, data: bytes, content_type="image/png", kind="photo", stored_type=None):
    """The whole client flow: get URL, PUT the bytes, confirm."""
    response = request_upload(api, data, content_type, kind)
    assert response.status_code == 201, response.json()
    media = MediaFile.objects.get(pk=response.json()["media_id"])
    get_storage().put(media.object_key, data, stored_type or content_type)
    return api.post(CONFIRM, {"media_id": str(media.pk)}, format="json")


# --- upload URL ---------------------------------------------------------------------


def test_upload_url_is_signed_for_type_and_exact_size(api, user):
    data = png_bytes()
    response = request_upload(api, data, "image/png", "photo")
    assert response.status_code == 201
    body = response.json()
    media = MediaFile.objects.get(pk=body["media_id"])
    assert media.owner == user
    assert media.status == MediaStatus.PENDING_UPLOAD
    assert media.object_key == f"users/{user.pk}/photo/{media.pk}.png"
    assert body["method"] == "PUT"
    assert body["headers"] == {
        "Content-Type": "image/png",
        "x-goog-content-length-range": f"1,{len(data)}",
    }
    assert "X-Goog-Expires=900" in body["upload_url"]


def test_checksum_is_bound_into_the_upload(api):
    data = png_bytes()
    md5 = hashlib.md5(data).hexdigest()  # noqa: S324
    body = request_upload(api, data, "image/png", "photo", checksum_md5=md5).json()
    assert body["headers"]["Content-MD5"]
    assert MediaFile.objects.get(pk=body["media_id"]).checksum_md5 == md5


@pytest.mark.parametrize(
    ("kind", "content_type", "size", "message"),
    [
        ("avatar", "video/mp4", 100, "avatar must be one of"),
        ("video", "image/png", 100, "video must be one of"),
        ("document", "image/webp", 100, "document must be one of"),
        ("avatar", "image/png", 5 * MB + 1, "at most 5 MB"),
        ("photo", "image/jpeg", 10 * MB + 1, "at most 10 MB"),
        ("video", "video/mp4", 100 * MB + 1, "at most 100 MB"),
        ("document", "application/pdf", 10 * MB + 1, "at most 10 MB"),
    ],
)
def test_type_and_size_caps_per_kind(api, kind, content_type, size, message):
    body = {"kind": kind, "content_type": content_type, "size_bytes": size}
    response = api.post(UPLOAD_URL, body, format="json")
    assert response.status_code == 400
    assert response.json()["code"] == "upload_not_allowed"
    assert message in response.json()["message"]
    assert not MediaFile.objects.exists()


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "photo", "content_type": "image/gif", "size_bytes": 10},
        {"kind": "photo", "content_type": "text/html", "size_bytes": 10},
        {"kind": "selfie", "content_type": "image/png", "size_bytes": 10},
        {"kind": "photo", "content_type": "image/png", "size_bytes": 0},
        {"kind": "photo", "content_type": "image/png", "size_bytes": 10, "checksum_md5": "xyz"},
    ],
)
def test_upload_request_validation(api, body):
    response = api.post(UPLOAD_URL, body, format="json")
    assert response.status_code == 400
    assert response.json()["code"] == "validation_error"


def test_pending_uploads_are_capped(api, settings):
    settings.MEDIA_MAX_PENDING_UPLOADS = 2
    for _ in range(2):
        assert request_upload(api, PDF, "application/pdf", "document").status_code == 201
    response = request_upload(api, PDF, "application/pdf", "document")
    assert response.status_code == 400
    assert "unfinished uploads" in response.json()["message"]


def test_upload_url_needs_sign_in():
    response = APIClient().post(UPLOAD_URL, {}, format="json")
    assert response.status_code == 401


def test_upload_url_is_rate_limited(api, monkeypatch):
    from apps.media.throttles import UploadUrlThrottle

    monkeypatch.setattr(UploadUrlThrottle, "THROTTLE_RATES", {"media_upload": "2/min"})
    for _ in range(2):
        request_upload(api, PDF, "application/pdf", "document")
    assert request_upload(api, PDF, "application/pdf", "document").status_code == 429


def test_missing_bucket_is_503(api, settings):
    from apps.media import storage

    settings.MEDIA_STORAGE_CLASS = "apps.media.storage.GCSMediaStorage"
    settings.MEDIA_BUCKET = ""
    storage._build.cache_clear()
    response = request_upload(api, PDF, "application/pdf", "document")
    assert response.status_code == 503
    assert response.json()["code"] == "media_storage_unavailable"


# --- confirm and processing ---------------------------------------------------------


def test_image_is_confirmed_resized_and_served_signed(api, user):
    data = png_bytes()
    response = upload(api, data)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["scan_status"] == "skipped"
    assert body["checksum_md5"] == hashlib.md5(data).hexdigest()  # noqa: S324
    assert body["url"].startswith("https://storage.test/read/users/")
    assert "X-Goog-Expires=300" in body["url"]
    assert set(body["variants"]) == {"thumb", "medium"}

    storage = get_storage()
    media = MediaFile.objects.get(pk=body["id"])
    with Image.open(io.BytesIO(storage.read(media.variants["thumb"]))) as thumb:
        assert thumb.format == "WEBP"
        assert max(thumb.size) == 320
    with Image.open(io.BytesIO(storage.read(media.variants["medium"]))) as medium:
        assert medium.size == (1280, 720)

    actions = list(
        AuditLog.objects.filter(object_id=str(media.pk)).values_list("action", flat=True)
    )
    assert sorted(actions) == ["media.confirmed", "media.ready"]


def test_small_images_are_not_enlarged(api):
    body = upload(api, png_bytes(size=(200, 100))).json()
    media = MediaFile.objects.get(pk=body["id"])
    with Image.open(io.BytesIO(get_storage().read(media.variants["medium"]))) as medium:
        assert medium.size == (200, 100)


@pytest.mark.parametrize(
    ("data", "content_type", "kind"),
    [(PDF, "application/pdf", "document"), (MP4, "video/mp4", "video")],
)
def test_non_images_are_ready_without_variants(api, data, content_type, kind):
    body = upload(api, data, content_type=content_type, kind=kind).json()
    assert body["status"] == "ready"
    assert body["variants"] == {}
    assert body["url"]


def test_confirm_is_idempotent(api):
    first = upload(api, PDF, "application/pdf", "document").json()
    again = api.post(CONFIRM, {"media_id": first["id"]}, format="json")
    assert again.status_code == 200
    assert again.json()["status"] == "ready"
    assert AuditLog.objects.filter(action="media.confirmed").count() == 1


def test_confirm_before_upload_is_409(api):
    media_id = request_upload(api, PDF, "application/pdf", "document").json()["media_id"]
    response = api.post(CONFIRM, {"media_id": media_id}, format="json")
    assert response.status_code == 409
    assert response.json()["code"] == "upload_not_found"
    assert MediaFile.objects.get(pk=media_id).status == MediaStatus.PENDING_UPLOAD


@pytest.mark.parametrize(
    ("declared", "stored_data", "stored_type", "reason"),
    [
        ("image/png", b"MZ\x90\x00" + b"\x00" * 60, "image/png", "not a valid image/png"),
        ("application/pdf", PDF, "text/html", "Uploaded as text/html"),
        ("image/jpeg", png_bytes(), "image/jpeg", "not a valid image/jpeg"),
    ],
)
def test_mismatched_files_are_rejected_and_deleted(api, declared, stored_data, stored_type, reason):
    kind = "document" if declared == "application/pdf" else "photo"
    response = request_upload(api, stored_data, declared, kind)
    media = MediaFile.objects.get(pk=response.json()["media_id"])
    get_storage().put(media.object_key, stored_data, stored_type)

    confirm = api.post(CONFIRM, {"media_id": str(media.pk)}, format="json")
    assert confirm.status_code == 422
    assert confirm.json()["code"] == "upload_rejected"
    assert reason in confirm.json()["message"]
    media.refresh_from_db()
    assert media.status == MediaStatus.REJECTED
    assert get_storage().stat(media.object_key) is None
    assert AuditLog.objects.get(action="media.rejected").after["status"] == "rejected"
    # Asking again gives the same answer.
    assert api.post(CONFIRM, {"media_id": str(media.pk)}, format="json").status_code == 422


def test_size_must_match_what_was_declared(api):
    response = request_upload(api, PDF, "application/pdf", "document")
    media = MediaFile.objects.get(pk=response.json()["media_id"])
    get_storage().put(media.object_key, PDF + b"extra", "application/pdf")
    confirm = api.post(CONFIRM, {"media_id": str(media.pk)}, format="json")
    assert confirm.status_code == 422
    assert "expected" in confirm.json()["message"]


def test_checksum_mismatch_is_rejected(api):
    md5 = hashlib.md5(b"something else").hexdigest()  # noqa: S324
    response = request_upload(api, PDF, "application/pdf", "document", checksum_md5=md5)
    media = MediaFile.objects.get(pk=response.json()["media_id"])
    get_storage().put(media.object_key, PDF, "application/pdf")
    confirm = api.post(CONFIRM, {"media_id": str(media.pk)}, format="json")
    assert confirm.status_code == 422
    assert "Checksum" in confirm.json()["message"]


def test_corrupt_image_with_valid_header_is_rejected(api):
    data = png_bytes()[:40]  # right signature, truncated body
    body = upload(api, data).json()
    media = MediaFile.objects.get(pk=body["id"])
    assert media.status == MediaStatus.REJECTED
    assert "Unreadable image" in media.rejection_reason
    assert get_storage().stat(media.object_key) is None
    assert body["url"] is None


# --- access -------------------------------------------------------------------------


def test_other_users_cannot_confirm_or_read(api):
    media_id = upload(api, PDF, "application/pdf", "document").json()["id"]
    stranger = APIClient()
    stranger.force_authenticate(VendorFactory())
    assert stranger.post(CONFIRM, {"media_id": media_id}, format="json").status_code == 404
    assert stranger.get(reverse("media:detail", args=[media_id])).status_code == 404


def test_owner_and_admins_get_fresh_signed_urls(api):
    media_id = upload(api, PDF, "application/pdf", "document").json()["id"]
    url = reverse("media:detail", args=[media_id])
    assert api.get(url).json()["url"].startswith("https://storage.test/read/")
    admin = APIClient()
    admin.force_authenticate(AdminUserFactory())
    assert admin.get(url).json()["url"]
    # An admin can look, but can't confirm someone else's upload.
    assert admin.post(CONFIRM, {"media_id": media_id}, format="json").status_code == 404


def test_pending_files_have_no_url(api):
    media_id = request_upload(api, PDF, "application/pdf", "document").json()["media_id"]
    body = api.get(reverse("media:detail", args=[media_id])).json()
    assert body["status"] == "pending_upload"
    assert body["url"] is None
    assert body["url_expires_at"] is None


# --- virus scan hook ----------------------------------------------------------------


class InfectedScanner:
    def scan(self, *, storage, key, content_type):
        from apps.media.scanning import ScanResult

        return ScanResult(ScanStatus.INFECTED, "EICAR-Test-Signature")


class CleanScanner:
    def scan(self, *, storage, key, content_type):
        from apps.media.scanning import ScanResult

        return ScanResult(ScanStatus.CLEAN)


class BrokenScanner:
    def scan(self, *, storage, key, content_type):
        raise ConnectionError("scanner down")


def use_scanner(settings, cls):
    from apps.media import scanning

    settings.MEDIA_VIRUS_SCANNER = f"{__name__}.{cls.__name__}"
    scanning._build.cache_clear()


def test_infected_files_are_quarantined_and_deleted(api, settings):
    use_scanner(settings, InfectedScanner)
    body = upload(api, PDF, "application/pdf", "document").json()
    media = MediaFile.objects.get(pk=body["id"])
    assert media.status == MediaStatus.QUARANTINED
    assert media.scan_status == ScanStatus.INFECTED
    assert get_storage().stat(media.object_key) is None
    assert body["url"] is None
    assert AuditLog.objects.filter(action="media.quarantined", object_id=str(media.pk)).exists()


def test_require_scan_holds_back_unscanned_files(api, settings):
    settings.MEDIA_REQUIRE_SCAN = True
    body = upload(api, PDF, "application/pdf", "document").json()
    assert body["status"] == "processing"
    assert body["scan_status"] == "skipped"
    assert body["url"] is None


def test_require_scan_serves_clean_files(api, settings):
    settings.MEDIA_REQUIRE_SCAN = True
    use_scanner(settings, CleanScanner)
    body = upload(api, PDF, "application/pdf", "document").json()
    assert body["status"] == "ready"
    assert body["scan_status"] == "clean"
    assert body["url"]


def test_scanner_failure_leaves_file_processing(api, settings, caplog):
    use_scanner(settings, BrokenScanner)
    body = upload(api, PDF, "application/pdf", "document").json()
    assert body["status"] == "processing"
    assert body["scan_status"] == "error"
    assert "Task failed" in caplog.text
