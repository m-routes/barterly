"""ClamdVirusScanner against a fake clamd speaking the INSTREAM protocol."""

import socket
import struct
import threading
from datetime import timedelta

import pytest

from apps.media.models import ScanStatus
from apps.media.scanning import ClamdVirusScanner, ScannerUnavailable
from apps.media.storage import check_link_lifetime
from apps.media.tests.fakes import InMemoryMediaStorage

EICAR = rb"X5O!P%@AP[4\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


class FakeClamd:
    """Accepts one INSTREAM, records the bytes, answers like clamd."""

    def __init__(self, reply_for=None):
        self.server = socket.create_server(("127.0.0.1", 0))
        self.port = self.server.getsockname()[1]
        self.received = b""
        self.reply_for = reply_for or (
            lambda data: b"stream: Eicar-Signature FOUND\0" if EICAR in data else b"stream: OK\0"
        )
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _recv(self, conn, n):
        buf = b""
        while len(buf) < n:
            part = conn.recv(n - len(buf))
            if not part:
                raise ConnectionError
            buf += part
        return buf

    def _serve(self):
        conn, _ = self.server.accept()
        with conn:
            assert self._recv(conn, 10) == b"zINSTREAM\0"
            while True:
                (size,) = struct.unpack("!L", self._recv(conn, 4))
                if size == 0:
                    break
                self.received += self._recv(conn, size)
            conn.sendall(self.reply_for(self.received))
        self.server.close()


@pytest.fixture
def storage():
    return InMemoryMediaStorage()


def scan(storage, clamd, data):
    storage.write("k", data, content_type="application/pdf")
    scanner = ClamdVirusScanner(host="127.0.0.1", port=clamd.port, timeout=5)
    scanner.CHUNK = 7  # several chunks even for small files
    return scanner.scan(storage=storage, key="k", content_type="application/pdf")


def test_clean_file_streams_every_byte(storage):
    clamd = FakeClamd()
    data = b"%PDF-1.7 a perfectly ordinary file" * 3
    assert scan(storage, clamd, data).status == ScanStatus.CLEAN
    clamd.thread.join(2)
    assert clamd.received == data


def test_eicar_is_infected(storage):
    result = scan(storage, FakeClamd(), b"prefix " + EICAR)
    assert result.status == ScanStatus.INFECTED
    assert result.detail == "Eicar-Signature FOUND"


def test_clamd_errors_raise_so_the_task_retries(storage):
    clamd = FakeClamd(reply_for=lambda data: b"INSTREAM size limit exceeded. ERROR\0")
    with pytest.raises(ScannerUnavailable):
        scan(storage, clamd, b"x" * 20)


def test_unreachable_clamd_raises(storage):
    storage.write("k", b"data", content_type="image/png")
    with socket.create_server(("127.0.0.1", 0)) as s:
        port = s.getsockname()[1]
    with pytest.raises(ScannerUnavailable):
        ClamdVirusScanner(host="127.0.0.1", port=port, timeout=1).scan(
            storage=storage, key="k", content_type="image/png"
        )


def test_clamav_host_switches_scanning_on():
    import subprocess
    import sys

    code = (
        "from django.conf import settings as s;print(s.MEDIA_VIRUS_SCANNER, s.MEDIA_REQUIRE_SCAN)"
    )
    out = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "manage.py", "shell", "-c", code],
        env={**__import__("os").environ, "CLAMAV_HOST": "localhost"},
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert out[-2:] == ["apps.media.scanning.ClamdVirusScanner", "True"]


def test_signed_links_are_short_lived(settings):
    assert settings.MEDIA_MAX_SIGNED_URL_SECONDS <= 900
    assert settings.MEDIA_UPLOAD_URL_SECONDS <= settings.MEDIA_MAX_SIGNED_URL_SECONDS
    assert settings.MEDIA_READ_URL_SECONDS <= settings.MEDIA_MAX_SIGNED_URL_SECONDS
    check_link_lifetime(timedelta(seconds=900))
    with pytest.raises(ValueError, match="at most"):
        check_link_lifetime(timedelta(hours=1))
