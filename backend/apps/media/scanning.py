"""Virus scan hook.

Every confirmed upload goes through the scanner named by MEDIA_VIRUS_SCANNER before it
is served. No scanner is wired up yet: NoopVirusScanner reports "skipped". To add one
(e.g. ClamAV on Cloud Run, or a scanning API), implement VirusScanner.scan and point
the setting at it. With MEDIA_REQUIRE_SCAN on, files that weren't scanned clean are
never served.
"""

from dataclasses import dataclass
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string

from apps.media.models import ScanStatus
from apps.media.storage import MediaStorage


@dataclass(frozen=True)
class ScanResult:
    status: ScanStatus  # CLEAN, INFECTED or SKIPPED; raise on scanner failure
    detail: str = ""


class VirusScanner(Protocol):
    def scan(self, *, storage: MediaStorage, key: str, content_type: str) -> ScanResult: ...


class NoopVirusScanner:
    def scan(self, *, storage, key, content_type):
        return ScanResult(ScanStatus.SKIPPED, "no scanner configured")


@cache
def _build(path: str) -> VirusScanner:
    return import_string(path)()


def get_scanner() -> VirusScanner:
    return _build(settings.MEDIA_VIRUS_SCANNER)
