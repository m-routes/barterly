import pytest
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.accounts.tests.factories import TalentFactory
from apps.common.models import AuditLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client):
    superuser = User.objects.create_superuser("+919876599999", "admin-pass-123")
    client.force_login(superuser)
    client.superuser = superuser
    return client


def change_payload(user, **overrides):
    data = {
        "phone": user.phone,
        "email": user.email or "",
        "role": user.role,
        "is_active": "on" if user.is_active else "",
    }
    data.update(overrides)
    return {k: v for k, v in data.items() if v != ""}


def test_changelist_and_add_page_render(admin_client):
    TalentFactory()
    assert admin_client.get(reverse("admin:accounts_user_changelist")).status_code == 200
    assert admin_client.get(reverse("admin:accounts_user_add")).status_code == 200


def test_add_user_through_admin(admin_client):
    response = admin_client.post(
        reverse("admin:accounts_user_add"),
        {"phone": "98765 11111", "email": "", "role": Role.VENDOR, "usable_password": "false"},
    )
    assert response.status_code == 302, response.content
    user = User.objects.get(phone="+919876511111")
    assert user.role == Role.VENDOR
    assert not user.has_usable_password()


def test_role_change_in_admin_is_audited(admin_client):
    user = TalentFactory()
    url = reverse("admin:accounts_user_change", args=[user.pk])
    response = admin_client.post(url, change_payload(user, role=Role.VENDOR, is_active=""))
    assert response.status_code == 302, response.content

    user.refresh_from_db()
    assert user.role == Role.VENDOR and not user.is_active
    entry = AuditLog.objects.get(action="user.updated")
    assert entry.actor == admin_client.superuser
    assert entry.before == {"role": "talent", "is_active": True}
    assert entry.after == {"role": "vendor", "is_active": False}


def test_other_edits_in_admin_log_only_the_admin_change(admin_client):
    user = TalentFactory()
    url = reverse("admin:accounts_user_change", args=[user.pk])
    response = admin_client.post(url, change_payload(user, email="new@example.com"))
    assert response.status_code == 302, response.content
    # Every admin action is audited, but there's no role or status change to record.
    entry = AuditLog.objects.get()
    assert entry.action == "admin.changed" and entry.actor == admin_client.superuser
    assert "Email" in entry.after["summary"]


def test_audit_log_admin_is_read_only(admin_client):
    AuditLog.objects.create(action="a.b", object_type="x.y", object_id="1")
    entry = AuditLog.objects.get()
    assert admin_client.get(reverse("admin:common_auditlog_changelist")).status_code == 200
    assert admin_client.get(reverse("admin:common_auditlog_add")).status_code == 403
    change_url = reverse("admin:common_auditlog_change", args=[entry.pk])
    assert admin_client.get(change_url).status_code == 200  # view only
    assert admin_client.post(change_url, {"action": "changed"}).status_code == 403
    delete_url = reverse("admin:common_auditlog_delete", args=[entry.pk])
    assert admin_client.get(delete_url).status_code == 403
