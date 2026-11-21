"""Virus scan hook.

Every confirmed upload goes through the scanner named by MEDIA_VIRUS_SCANNER before it
is served. ClamdVirusScanner streams the file to a clamd daemon (deployed as a sidecar
of the API service when Terraform's clamav_enabled is on; CLAMAV_HOST switches it on in
settings). NoopVirusScanner reports "skipped". With MEDIA_REQUIRE_SCAN on, files that
weren't scanned clean are never served.
"""

import socket
import struct
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


class ScannerUnavailable(Exception):
    """clamd couldn't be reached or answered oddly; the task retries."""


class ClamdVirusScanner:
    """clamd's INSTREAM command over TCP: the file goes in chunks, read from storage."""

    CHUNK = 1024 * 1024

    def __init__(self, host: str | None = None, port: int | None = None, timeout=None):
        self.host = host or settings.CLAMAV_HOST
        self.port = port or settings.CLAMAV_PORT
        self.timeout = timeout or settings.CLAMAV_TIMEOUT_SECONDS

    def scan(self, *, storage, key, content_type):
        stat = storage.stat(key)
        size = stat.size if stat else 0
        try:
            with socket.create_connection((self.host, self.port), timeout=self.timeout) as conn:
                conn.sendall(b"zINSTREAM\0")
                for start in range(0, size, self.CHUNK):
                    chunk = storage.read(key, start=start, end=min(start + self.CHUNK, size) - 1)
                    conn.sendall(struct.pack("!L", len(chunk)) + chunk)
                conn.sendall(struct.pack("!L", 0))
                reply = _read_reply(conn)
        except OSError as exc:
            raise ScannerUnavailable(f"clamd at {self.host}:{self.port}: {exc}") from exc
        # "stream: OK", "stream: Eicar-Signature FOUND", "INSTREAM size limit exceeded. ERROR"
        if reply.endswith("FOUND"):
            return ScanResult(ScanStatus.INFECTED, reply.removeprefix("stream:").strip())
        if reply.endswith("OK"):
            return ScanResult(ScanStatus.CLEAN)
        raise ScannerUnavailable(f"clamd answered {reply!r}")


def _read_reply(conn) -> str:
    data = b""
    while not data.endswith(b"\0"):
        part = conn.recv(4096)
        if not part:
            break
        data += part
    return data.rstrip(b"\0").decode(errors="replace").strip()


@cache
def _build(path: str) -> VirusScanner:
    return import_string(path)()


def get_scanner() -> VirusScanner:
    return _build(settings.MEDIA_VIRUS_SCANNER)
