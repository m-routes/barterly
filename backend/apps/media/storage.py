"""Object storage for media, behind a small interface.

Files never get a public URL: clients upload with a short-lived signed PUT URL and read
with a short-lived signed GET URL. GCSMediaStorage is the real implementation; tests use
apps.media.tests.fakes.InMemoryMediaStorage.
"""

import base64
import contextlib
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils import timezone
from django.utils.module_loading import import_string


class StorageNotConfigured(Exception):
    pass


@dataclass(frozen=True)
class StoredObject:
    size: int
    content_type: str
    md5_hex: str | None


@dataclass(frozen=True)
class SignedUpload:
    url: str
    expires_at: datetime
    method: str = "PUT"
    headers: dict[str, str] = field(default_factory=dict)  # the client must send these


class MediaStorage(Protocol):
    def signed_upload(
        self,
        key: str,
        *,
        content_type: str,
        max_bytes: int,
        md5_b64: str | None,
        expires: timedelta,
    ) -> SignedUpload: ...

    def signed_read_url(
        self, key: str, *, expires: timedelta, download_name: str | None = None
    ) -> str: ...

    def stat(self, key: str) -> StoredObject | None: ...

    def read(self, key: str, *, start: int = 0, end: int | None = None) -> bytes:
        """Bytes [start, end] inclusive (whole object from start when end is None)."""
        ...

    def write(self, key: str, data: bytes, *, content_type: str) -> None: ...

    def delete(self, key: str) -> None: ...


def upload_headers(content_type: str, max_bytes: int, md5_b64: str | None) -> dict[str, str]:
    """Headers baked into the signed upload; Cloud Storage refuses a PUT without them.

    x-goog-content-length-range makes Cloud Storage itself reject oversized bodies, and
    Content-MD5 (when the client gave a checksum) makes it reject corrupted ones.
    """
    headers = {"Content-Type": content_type, "x-goog-content-length-range": f"1,{max_bytes}"}
    if md5_b64:
        headers["Content-MD5"] = md5_b64
    return headers


class GCSMediaStorage:
    """The private media bucket (settings.MEDIA_BUCKET).

    On Cloud Run the runtime credentials have no private key, so URLs are signed through
    the IAM signBlob API as the runtime service account (the API's service account has
    Token Creator on itself).
    """

    def __init__(self, bucket_name: str | None = None):
        bucket_name = bucket_name or settings.MEDIA_BUCKET
        if not bucket_name:
            raise StorageNotConfigured("MEDIA_BUCKET (GS_MEDIA_BUCKET) is not set")
        import google.auth
        from google.cloud import storage

        self._credentials, project = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        self._client = storage.Client(project=project, credentials=self._credentials)
        self._bucket = self._client.bucket(bucket_name)
        self._lock = threading.Lock()

    def _signing_kwargs(self) -> dict:
        import google.auth.transport.requests
        from google.oauth2 import service_account

        if isinstance(self._credentials, service_account.Credentials):
            return {"credentials": self._credentials}  # a key file: sign locally

        with self._lock:
            if not self._credentials.valid:
                self._credentials.refresh(google.auth.transport.requests.Request())
        email = settings.GS_SA_EMAIL or getattr(self._credentials, "service_account_email", None)
        return {"service_account_email": email, "access_token": self._credentials.token}

    def signed_upload(self, key, *, content_type, max_bytes, md5_b64, expires):
        headers = upload_headers(content_type, max_bytes, md5_b64)
        url = self._bucket.blob(key).generate_signed_url(
            version="v4",
            method="PUT",
            expiration=expires,
            content_type=content_type,
            content_md5=md5_b64,
            headers={k: v for k, v in headers.items() if k.lower().startswith("x-goog-")},
            **self._signing_kwargs(),
        )
        return SignedUpload(url=url, expires_at=timezone.now() + expires, headers=headers)

    def signed_read_url(self, key, *, expires, download_name=None):
        disposition = f'inline; filename="{download_name}"' if download_name else None
        return self._bucket.blob(key).generate_signed_url(
            version="v4",
            method="GET",
            expiration=expires,
            response_disposition=disposition,
            **self._signing_kwargs(),
        )

    def stat(self, key):
        blob = self._bucket.get_blob(key)
        if blob is None:
            return None
        md5 = base64.b64decode(blob.md5_hash).hex() if blob.md5_hash else None
        return StoredObject(size=blob.size, content_type=blob.content_type or "", md5_hex=md5)

    def read(self, key, *, start=0, end=None):
        return self._bucket.blob(key).download_as_bytes(start=start, end=end)

    def write(self, key, data, *, content_type):
        self._bucket.blob(key).upload_from_string(data, content_type=content_type)

    def delete(self, key):
        from google.api_core.exceptions import NotFound

        with contextlib.suppress(NotFound):
            self._bucket.blob(key).delete()


@cache
def _build(path: str) -> MediaStorage:
    return import_string(path)()


def get_storage() -> MediaStorage:
    """The storage named by settings.MEDIA_STORAGE_CLASS (built once per process)."""
    return _build(settings.MEDIA_STORAGE_CLASS)
