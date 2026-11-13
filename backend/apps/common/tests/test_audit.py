import uuid
from decimal import Decimal

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory
from apps.common.models import AuditLog
from apps.common.request_context import reset_request_id, set_request_id
from apps.common.services.audit import client_ip, log_action, snapshot
from apps.profiles.tests.factories import TalentProfileFactory

pytestmark = pytest.mark.django_db
rf = RequestFactory()


def test_log_action_with_object_and_request():
    admin, target = AdminUserFactory(), TalentFactory()
    request = rf.post("/x", HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1")
    request.request_id = "req-12345678"

    entry = log_action(
        actor=admin,
        action="user.role_changed",
        obj=target,
        before={"role": "talent"},
        after={"role": "vendor"},
        request=request,
    )

    entry.refresh_from_db()
    assert entry.actor == admin
    assert entry.object_type == "accounts.user"
    assert entry.object_id == str(target.pk)
    assert entry.before == {"role": "talent"}
    assert entry.after == {"role": "vendor"}
    assert entry.ip == "203.0.113.7"
    assert entry.request_id == "req-12345678"
    assert entry.created_at is not None


def test_log_action_with_explicit_target_and_values_made_json_safe():
    entry = log_action(
        actor=None,
        action="payout.created",
        object_type="payments.payout",
        object_id=42,
        after={"amount": Decimal("1500.50"), "ref": uuid.UUID(int=1)},
    )
    entry.refresh_from_db()
    assert entry.object_id == "42"
    assert entry.after == {"amount": "1500.50", "ref": "00000000-0000-0000-0000-000000000001"}
    assert entry.before is None
    assert entry.actor is None


def test_anonymous_actor_is_stored_as_none():
    entry = log_action(actor=AnonymousUser(), action="a.b", object_type="x.y", object_id="1")
    assert entry.actor is None


def test_request_id_falls_back_to_context():
    token = set_request_id("ctx-request-id")
    try:
        entry = log_action(actor=None, action="a.b", object_type="x.y", object_id="1")
    finally:
        reset_request_id(token)
    assert entry.request_id == "ctx-request-id"


@pytest.mark.parametrize("kwargs", [{"action": ""}, {"object_type": None}, {"object_id": ""}])
def test_log_action_requires_action_and_target(kwargs):
    params = {"actor": None, "action": "a.b", "object_type": "x.y", "object_id": "1", **kwargs}
    with pytest.raises(ValueError):
        log_action(**params)
    assert not AuditLog.objects.exists()


def test_snapshot_uses_raw_fk_ids_and_json_types():
    profile = TalentProfileFactory(languages=["Hindi"])
    assert snapshot(profile, ["user", "languages", "full_name"]) == {
        "user": str(profile.user_id),
        "languages": ["Hindi"],
        "full_name": profile.full_name,
    }


@pytest.mark.parametrize(
    ("meta", "expected"),
    [
        ({"HTTP_X_FORWARDED_FOR": "198.51.100.2"}, "198.51.100.2"),
        ({"HTTP_X_FORWARDED_FOR": "2001:db8::1, 10.0.0.1"}, "2001:db8::1"),
        ({"REMOTE_ADDR": "192.0.2.10"}, "192.0.2.10"),
        ({"HTTP_X_FORWARDED_FOR": "not-an-ip"}, None),
        ({"REMOTE_ADDR": ""}, None),
    ],
)
def test_client_ip(meta, expected):
    request = rf.get("/")
    request.META.pop("REMOTE_ADDR", None)
    request.META.update(meta)
    assert client_ip(request) == expected


def test_client_ip_without_request():
    assert client_ip(None) is None
