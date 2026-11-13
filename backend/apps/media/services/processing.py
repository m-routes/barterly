"""The media.process task: virus scan, then resized copies for images.

Idempotent (only files in PROCESSING are touched), so a retried task is harmless.
"""

import io
import logging

from django.conf import settings
from django.db import transaction
from PIL import Image, ImageOps

from apps.media.models import MediaFile, MediaStatus, ScanStatus
from apps.media.policy import IMAGE_TYPES, WEBP
from apps.media.scanning import get_scanner
from apps.media.services.uploads import _set_status, mark_scanned
from apps.media.storage import get_storage
from apps.media.tasks import task

logger = logging.getLogger(__name__)

# Longest edge in pixels for each resized copy (WebP, EXIF stripped).
VARIANT_SIZES = {"thumb": 320, "medium": 1280}
# Refuse decompression bombs: a small file that expands to a huge bitmap.
Image.MAX_IMAGE_PIXELS = 50_000_000


@task("media.process")
def process_media(payload: dict) -> None:
    media = MediaFile.objects.filter(pk=payload["media_id"], status=MediaStatus.PROCESSING).first()
    if media is None:
        return
    storage = get_storage()

    try:
        result = get_scanner().scan(
            storage=storage, key=media.object_key, content_type=media.content_type
        )
    except Exception:
        logger.exception("Virus scan failed", extra={"media_id": str(media.pk)})
        mark_scanned(media, ScanStatus.ERROR)
        raise  # leave it in PROCESSING; a queue with retries will try again
    mark_scanned(media, result.status)

    if result.status == ScanStatus.INFECTED:
        storage.delete(media.object_key)
        with transaction.atomic():
            _set_status(
                media,
                MediaStatus.QUARANTINED,
                "media.quarantined",
                None,
                rejection_reason=f"Virus scan: {result.detail}"[:200],
            )
        logger.warning("Infected upload removed", extra={"media_id": str(media.pk)})
        return
    if result.status != ScanStatus.CLEAN and settings.MEDIA_REQUIRE_SCAN:
        logger.warning("Upload not scanned; held back", extra={"media_id": str(media.pk)})
        return

    if media.content_type in IMAGE_TYPES:
        try:
            media.variants = make_variants(storage, media)
        except (OSError, Image.DecompressionBombError, ValueError) as exc:
            # Pillow can't read it: corrupt, truncated or a bomb. Don't keep it.
            storage.delete(media.object_key)
            with transaction.atomic():
                _set_status(
                    media,
                    MediaStatus.REJECTED,
                    "media.rejected",
                    None,
                    rejection_reason=f"Unreadable image: {exc}"[:200],
                )
            return

    with transaction.atomic():
        _set_status(media, MediaStatus.READY, "media.ready", None, variants=media.variants)


def make_variants(storage, media: MediaFile) -> dict[str, str]:
    with Image.open(io.BytesIO(storage.read(media.object_key))) as original:
        original.load()
        image = ImageOps.exif_transpose(original)  # apply rotation; EXIF isn't copied
    if image.mode not in ("RGB", "RGBA"):
        image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
    stem = media.object_key.rsplit(".", 1)[0]
    variants = {}
    for label, edge in VARIANT_SIZES.items():
        copy = image.copy()
        copy.thumbnail((edge, edge), Image.Resampling.LANCZOS)
        out = io.BytesIO()
        copy.save(out, format="WEBP", quality=82, method=4)
        key = f"{stem}__{label}.webp"
        storage.write(key, out.getvalue(), content_type=WEBP)
        variants[label] = key
    return variants
