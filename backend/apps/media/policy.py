"""What may be uploaded: content types and size caps per kind, plus file signatures.

The declared content type is checked against the file's first bytes on confirm, so a
renamed executable can't pass as a JPEG.
"""

from dataclasses import dataclass

from django.db import models

MB = 1024 * 1024

JPEG, PNG, WEBP, MP4, PDF = "image/jpeg", "image/png", "image/webp", "video/mp4", "application/pdf"
IMAGE_TYPES = frozenset({JPEG, PNG, WEBP})
EXTENSIONS = {JPEG: ".jpg", PNG: ".png", WEBP: ".webp", MP4: ".mp4", PDF: ".pdf"}


class Kind(models.TextChoices):
    AVATAR = "avatar", "Profile photo"
    PHOTO = "photo", "Photo"
    VIDEO = "video", "Video"
    DOCUMENT = "document", "Document"


@dataclass(frozen=True)
class KindRule:
    content_types: frozenset[str]
    max_bytes: int


RULES: dict[str, KindRule] = {
    Kind.AVATAR: KindRule(IMAGE_TYPES, 5 * MB),
    Kind.PHOTO: KindRule(IMAGE_TYPES, 10 * MB),
    Kind.VIDEO: KindRule(frozenset({MP4}), 100 * MB),
    Kind.DOCUMENT: KindRule(frozenset({PDF, JPEG, PNG}), 10 * MB),
}

# Bytes needed from the start of a file to check its signature.
SIGNATURE_BYTES = 16


def matches_signature(content_type: str, head: bytes) -> bool:
    """True when the file's first bytes fit the declared content type."""
    if content_type == JPEG:
        return head.startswith(b"\xff\xd8\xff")
    if content_type == PNG:
        return head.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == WEBP:
        return head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    if content_type == MP4:
        return head[4:8] == b"ftyp"
    if content_type == PDF:
        return head.startswith(b"%PDF-")
    return False
