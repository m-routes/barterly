from unittest import mock

import pytest

from apps.media.policy import JPEG, MP4, PDF, PNG, WEBP, matches_signature
from apps.media.tasks import InlineTaskQueue, run_task, task


@pytest.mark.parametrize(
    ("content_type", "head", "ok"),
    [
        (JPEG, b"\xff\xd8\xff\xe0" + b"\x00" * 12, True),
        (JPEG, b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, False),
        (PNG, b"\x89PNG\r\n\x1a\n" + b"\x00" * 8, True),
        (WEBP, b"RIFF\x00\x00\x00\x00WEBPVP8 ", True),
        (WEBP, b"RIFF\x00\x00\x00\x00WAVEfmt ", False),
        (MP4, b"\x00\x00\x00\x18ftypisom" + b"\x00" * 4, True),
        (PDF, b"%PDF-1.4\n", True),
        (PDF, b"<html>", False),
        ("image/gif", b"GIF89a", False),
    ],
)
def test_signatures(content_type, head, ok):
    assert matches_signature(content_type, head) is ok


def test_tasks_run_by_name():
    calls = []

    @task("test.echo")
    def echo(payload):
        calls.append(payload)

    run_task("test.echo", {"a": 1})
    InlineTaskQueue().enqueue("test.echo", {"a": 2})
    assert calls == [{"a": 1}, {"a": 2}]


def test_unknown_task_is_an_error():
    with pytest.raises(LookupError):
        run_task("nope", {})


def test_inline_queue_logs_failures_instead_of_raising(caplog):
    @task("test.boom")
    def boom(payload):
        raise RuntimeError("boom")

    InlineTaskQueue().enqueue("test.boom", {})
    assert "Task failed" in caplog.text


@pytest.mark.django_db
def test_processing_skips_files_not_in_processing():
    from apps.media.services.processing import process_media

    with mock.patch("apps.media.services.processing.get_scanner") as scanner:
        process_media({"media_id": "00000000-0000-0000-0000-000000000000"})
    scanner.assert_not_called()
