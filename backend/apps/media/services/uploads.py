"""Upload lifecycle: signed upload URL -> client PUT -> confirm -> processing -> ready.

Status changes are audit-logged (media.confirmed, media.rejected, media.quarantined).
"""

import base64
import logging
from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.services.audit import log_action
from apps.media.models import MediaFile, MediaStatus, ScanStatus
from apps.media.policy import EXTENSIONS, RULES, SIGNATURE_BYTES, matches_signature
from apps.media.storage import SignedUpload, get_storage
from apps.media.tasks import get_queue

logger = logging.getLogger(__name__)


class UploadNotAllowed(Exception):
    """The request breaks the upload policy (type, size, too many pending)."""


class UploadNotReady(Exception):
    """Confirm was called before the file reached storage."""


class UploadRejected(Exception):
    """The stored file failed checks; it has been deleted."""


@dataclass(frozen=True)
class PreparedUpload:
    media: MediaFile
    upload: SignedUpload


def md5_hex_to_b64(md5_hex: str) -> str:
    try:
        raw = bytes.fromhex(md5_hex)
    except ValueError as exc:
        raise UploadNotAllowed("checksum_md5 must be 32 hex characters.") from exc
    if len(raw) != 16:
        raise UploadNotAllowed("checksum_md5 must be 32 hex characters.")
    return base64.b64encode(raw).decode()


def prepare_upload(
    *, owner, kind: str, content_type: str, size_bytes: int, checksum_md5: str = ""
) -> PreparedUpload:
    rule = RULES[kind]
    if content_type not in rule.content_types:
        allowed = ", ".join(sorted(rule.content_types))
        raise UploadNotAllowed(f"A {kind} must be one of: {allowed}.")
    if size_bytes > rule.max_bytes:
        raise UploadNotAllowed(f"A {kind} can be at most {rule.max_bytes // (1024 * 1024)} MB.")
    pending = MediaFile.objects.filter(
        owner=owner, status=MediaStatus.PENDING_UPLOAD, upload_expires_at__gt=timezone.now()
    ).count()
    if pending >= settings.MEDIA_MAX_PENDING_UPLOADS:
        raise UploadNotAllowed("Too many unfinished uploads. Finish or wait for them to expire.")
    md5_b64 = md5_hex_to_b64(checksum_md5) if checksum_md5 else None

    expires = timedelta(seconds=settings.MEDIA_UPLOAD_URL_SECONDS)
    media = MediaFile(
        owner=owner,
        kind=kind,
        content_type=content_type,
        size_bytes=size_bytes,
        checksum_md5=checksum_md5.lower(),
        upload_expires_at=timezone.now() + expires,
    )
    media.object_key = f"users/{owner.pk}/{kind}/{media.id}{EXTENSIONS[content_type]}"
    media.save()
    upload = get_storage().signed_upload(
        media.object_key,
        content_type=content_type,
        max_bytes=size_bytes,
        md5_b64=md5_b64,
        expires=expires,
    )
    return PreparedUpload(media=media, upload=upload)


def confirm_upload(media: MediaFile, *, request=None) -> MediaFile:
    """Check the stored object against what was declared, then hand it to processing.

    Idempotent: confirming a file that is already past the upload step returns it.
    """
    storage = get_storage()
    with transaction.atomic():
        media = MediaFile.objects.select_for_update().get(pk=media.pk)
        if media.status != MediaStatus.PENDING_UPLOAD:
            if media.status == MediaStatus.REJECTED:
                raise UploadRejected(media.rejection_reason)
            return media
        stored = storage.stat(media.object_key)
        if stored is None:
            raise UploadNotReady
        problem = _check(media, stored, storage)
        if problem:
            storage.delete(media.object_key)
            _set_status(
                media, MediaStatus.REJECTED, "media.rejected", request, rejection_reason=problem
            )
        else:
            media.checksum_md5 = stored.md5_hex or media.checksum_md5
            media.confirmed_at = timezone.now()
            _set_status(media, MediaStatus.PROCESSING, "media.confirmed", request)
    if media.status == MediaStatus.REJECTED:
        raise UploadRejected(media.rejection_reason)
    get_queue().enqueue("media.process", {"media_id": str(media.pk)})
    media.refresh_from_db()
    return media


def _check(media: MediaFile, stored, storage) -> str:
    rule = RULES[media.kind]
    if stored.content_type != media.content_type:
        return (
            f"Uploaded as {stored.content_type or 'unknown type'}, expected {media.content_type}."
        )
    if stored.size != media.size_bytes:
        return f"Uploaded {stored.size} bytes, expected {media.size_bytes}."
    if stored.size > rule.max_bytes:
        return "File is larger than allowed."
    if media.checksum_md5 and stored.md5_hex and stored.md5_hex != media.checksum_md5:
        return "Checksum does not match."
    head = storage.read(media.object_key, start=0, end=SIGNATURE_BYTES - 1)
    if not matches_signature(media.content_type, head):
        return f"File contents are not a valid {media.content_type}."
    return ""


def _set_status(media: MediaFile, new_status: str, action: str, request, **fields) -> None:
    before = {"status": media.status}
    media.status = new_status
    for name, value in fields.items():
        setattr(media, name, value)
    media.save()
    log_action(
        actor=media.owner if request is None else request.user,
        action=action,
        obj=media,
        before=before,
        after={"status": new_status, **fields},
        request=request,
    )


def mark_scanned(media: MediaFile, scan_status: str) -> None:
    media.scan_status = scan_status
    media.scanned_at = timezone.now()
    media.save(update_fields=["scan_status", "scanned_at", "updated_at"])


def is_servable(media: MediaFile) -> bool:
    if media.status != MediaStatus.READY:
        return False
    if settings.MEDIA_REQUIRE_SCAN:
        return media.scan_status == ScanStatus.CLEAN
    return True


def read_urls(media: MediaFile) -> dict:
    """Short-lived signed GET URLs for the file and its variants, if it may be served."""
    if not is_servable(media):
        return {"url": None, "variants": {}, "expires_at": None}
    storage = get_storage()
    expires = timedelta(seconds=settings.MEDIA_READ_URL_SECONDS)
    name = f"{media.kind}{EXTENSIONS.get(media.content_type, '')}"
    return {
        "url": storage.signed_read_url(media.object_key, expires=expires, download_name=name),
        "variants": {
            label: storage.signed_read_url(key, expires=expires)
            for label, key in media.variants.items()
        },
        "expires_at": timezone.now() + expires,
    }
