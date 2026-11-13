"""GCSMediaStorage against a mocked google-cloud-storage client: no network."""

import base64
from datetime import timedelta
from unittest import mock

import pytest
from google.api_core.exceptions import NotFound

from apps.media.storage import GCSMediaStorage, StorageNotConfigured


class FakeComputeCredentials:
    """Like Cloud Run's metadata-server credentials: a token, no private key."""

    service_account_email = "api@project.iam.gserviceaccount.com"

    def __init__(self):
        self.valid = False
        self.token = None

    def refresh(self, request):
        self.valid, self.token = True, "access-token"


@pytest.fixture
def gcs(settings):
    settings.GS_SA_EMAIL = None
    creds = FakeComputeCredentials()
    with (
        mock.patch("google.auth.default", return_value=(creds, "project")),
        mock.patch("google.cloud.storage.Client") as client_cls,
    ):
        storage = GCSMediaStorage(bucket_name="media-bucket")
    bucket = client_cls.return_value.bucket.return_value
    client_cls.return_value.bucket.assert_called_once_with("media-bucket")
    return storage, bucket


def test_requires_a_bucket(settings):
    settings.MEDIA_BUCKET = ""
    with pytest.raises(StorageNotConfigured):
        GCSMediaStorage()


def test_signed_upload_binds_type_size_and_checksum_and_signs_via_iam(gcs):
    storage, bucket = gcs
    blob = bucket.blob.return_value
    blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed"
    result = storage.signed_upload(
        "users/u/photo/x.png",
        content_type="image/png",
        max_bytes=1234,
        md5_b64="abc==",
        expires=timedelta(minutes=15),
    )
    assert result.url == "https://storage.googleapis.com/signed"
    assert result.headers == {
        "Content-Type": "image/png",
        "x-goog-content-length-range": "1,1234",
        "Content-MD5": "abc==",
    }
    kwargs = blob.generate_signed_url.call_args.kwargs
    assert kwargs["method"] == "PUT"
    assert kwargs["version"] == "v4"
    assert kwargs["content_type"] == "image/png"
    assert kwargs["content_md5"] == "abc=="
    assert kwargs["headers"] == {"x-goog-content-length-range": "1,1234"}
    assert kwargs["service_account_email"] == "api@project.iam.gserviceaccount.com"
    assert kwargs["access_token"] == "access-token"  # noqa: S105


def test_signed_read_url_is_get_with_disposition(gcs):
    storage, bucket = gcs
    storage.signed_read_url("k", expires=timedelta(minutes=5), download_name="photo.png")
    kwargs = bucket.blob.return_value.generate_signed_url.call_args.kwargs
    assert kwargs["method"] == "GET"
    assert kwargs["expiration"] == timedelta(minutes=5)
    assert kwargs["response_disposition"] == 'inline; filename="photo.png"'


def test_stat_read_write_delete(gcs):
    storage, bucket = gcs
    bucket.get_blob.return_value = None
    assert storage.stat("missing") is None

    blob = mock.Mock(size=10, content_type="application/pdf")
    blob.md5_hash = base64.b64encode(bytes.fromhex("00" * 15 + "ff")).decode()
    bucket.get_blob.return_value = blob
    stored = storage.stat("k")
    assert (stored.size, stored.content_type, stored.md5_hex) == (
        10,
        "application/pdf",
        "00" * 15 + "ff",
    )

    storage.read("k", start=0, end=15)
    bucket.blob.return_value.download_as_bytes.assert_called_with(start=0, end=15)
    storage.write("k2", b"data", content_type="image/webp")
    bucket.blob.return_value.upload_from_string.assert_called_with(
        b"data", content_type="image/webp"
    )
    bucket.blob.return_value.delete.side_effect = NotFound("gone")
    storage.delete("k")  # already gone: fine
