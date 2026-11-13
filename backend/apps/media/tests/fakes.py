"""Test-only in-memory stand-in for the media bucket."""

import hashlib
from urllib.parse import urlencode

from django.utils import timezone

from apps.media.storage import SignedUpload, StoredObject, upload_headers


class InMemoryMediaStorage:
    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}
        self.signed: list[tuple[str, str]] = []  # (method, key)

    # What a client does with the signed URL.
    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def signed_upload(self, key, *, content_type, max_bytes, md5_b64, expires):
        self.signed.append(("PUT", key))
        query = urlencode({"X-Goog-Expires": int(expires.total_seconds())})
        return SignedUpload(
            url=f"https://storage.test/upload/{key}?{query}",
            expires_at=timezone.now() + expires,
            headers=upload_headers(content_type, max_bytes, md5_b64),
        )

    def signed_read_url(self, key, *, expires, download_name=None):
        self.signed.append(("GET", key))
        return f"https://storage.test/read/{key}?X-Goog-Expires={int(expires.total_seconds())}"

    def stat(self, key):
        if key not in self.objects:
            return None
        data, content_type = self.objects[key]
        return StoredObject(len(data), content_type, hashlib.md5(data).hexdigest())  # noqa: S324

    def read(self, key, *, start=0, end=None):
        data = self.objects[key][0]
        return data[start : None if end is None else end + 1]

    def write(self, key, data, *, content_type):
        self.objects[key] = (data, content_type)

    def delete(self, key):
        self.objects.pop(key, None)
