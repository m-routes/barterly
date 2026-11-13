import pytest
from django.test import RequestFactory

from apps.accounts.models import Role
from apps.accounts.services.users import audit_user_change, change_role, set_active
from apps.accounts.tests.factories import AdminUserFactory, TalentFactory
from apps.common.models import AuditLog

pytestmark = pytest.mark.django_db


def test_change_role_updates_and_audits():
    admin, user = AdminUserFactory(), TalentFactory()
    request = RequestFactory().post("/", REMOTE_ADDR="192.0.2.1")

    result = change_role(user, Role.VENDOR, actor=admin, request=request)

    user.refresh_from_db()
    assert user.role == Role.VENDOR and result.role == Role.VENDOR
    entry = AuditLog.objects.get()
    assert entry.action == "user.role_changed"
    assert entry.actor == admin
    assert entry.object_id == str(user.pk)
    assert entry.before == {"role": "talent"}
    assert entry.after == {"role": "vendor"}
    assert entry.ip == "192.0.2.1"


def test_unchanged_role_is_not_logged():
    user = TalentFactory()
    change_role(user, Role.TALENT, actor=None)
    assert not AuditLog.objects.exists()


def test_unknown_role_is_rejected():
    with pytest.raises(ValueError):
        change_role(TalentFactory(), "guest", actor=None)
    assert not AuditLog.objects.exists()


def test_deactivate_and_reactivate_are_audited():
    admin, user = AdminUserFactory(), TalentFactory()
    set_active(user, False, actor=admin)
    assert user.is_active is False
    set_active(user, True, actor=admin)
    user.refresh_from_db()
    assert user.is_active is True
    actions = list(AuditLog.objects.order_by("id").values_list("action", "before", "after"))
    assert actions == [
        ("user.deactivated", {"is_active": True}, {"is_active": False}),
        ("user.activated", {"is_active": False}, {"is_active": True}),
    ]


def test_audit_user_change_logs_only_changed_audited_fields():
    admin, user = AdminUserFactory(), TalentFactory(is_staff=True)
    audit_user_change(user, {"role": Role.VENDOR, "is_staff": True}, actor=admin)
    entry = AuditLog.objects.get()
    assert entry.action == "user.updated"
    assert entry.before == {"role": "vendor"}
    assert entry.after == {"role": "talent"}


def test_audit_user_change_without_changes_logs_nothing():
    user = TalentFactory()
    audit_user_change(user, {"role": Role.TALENT}, actor=None)
    audit_user_change(user, {}, actor=None)
    assert not AuditLog.objects.exists()
