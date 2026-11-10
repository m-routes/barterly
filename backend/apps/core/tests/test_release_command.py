from io import StringIO
from unittest import mock

from django.core.management import call_command


def test_release_runs_migrate_then_collectstatic():
    out = StringIO()
    with mock.patch("apps.core.management.commands.release.call_command") as inner:
        call_command("release", stdout=out)
    assert [c.args[0] for c in inner.call_args_list] == ["migrate", "collectstatic"]
    for c in inner.call_args_list:
        assert c.kwargs["interactive"] is False
    assert "Release tasks complete" in out.getvalue()


def test_release_can_skip_static():
    out = StringIO()
    with mock.patch("apps.core.management.commands.release.call_command") as inner:
        call_command("release", "--skip-static", stdout=out)
    assert [c.args[0] for c in inner.call_args_list] == ["migrate"]
    assert "Skipping collectstatic" in out.getvalue()
