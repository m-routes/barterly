from io import StringIO
from unittest import mock

from django.core.management import call_command

RELEASE = "apps.core.management.commands.release"


def test_release_runs_migrate_then_collectstatic():
    out = StringIO()
    with (
        mock.patch(f"{RELEASE}.call_command") as inner,
        mock.patch(f"{RELEASE}.switch_to_custom_user", return_value=[]) as switch,
    ):
        call_command("release", stdout=out)
    switch.assert_called_once()
    assert [c.args[0] for c in inner.call_args_list] == ["migrate", "collectstatic"]
    for c in inner.call_args_list:
        assert c.kwargs["interactive"] is False
    assert "Release tasks complete" in out.getvalue()


def test_release_can_skip_static():
    out = StringIO()
    with (
        mock.patch(f"{RELEASE}.call_command") as inner,
        mock.patch(f"{RELEASE}.switch_to_custom_user", return_value=[]),
    ):
        call_command("release", "--skip-static", stdout=out)
    assert [c.args[0] for c in inner.call_args_list] == ["migrate"]
    assert "Skipping collectstatic" in out.getvalue()


def test_release_reports_the_user_model_switch():
    out = StringIO()
    with (
        mock.patch(f"{RELEASE}.call_command"),
        mock.patch(f"{RELEASE}.switch_to_custom_user", return_value=["auth_user"]),
    ):
        call_command("release", stdout=out)
    assert "dropped empty tables: ['auth_user']" in out.getvalue()
