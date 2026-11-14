from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client
from django.utils import timezone

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.backoffice.roles import PERMISSIONS, AdminRole, roles_of, sync_roles
from apps.backoffice.rules import gig_rules
from apps.common.models import AuditLog
from apps.gigs.constants import GigStatus
from apps.gigs.models import Gig
from apps.gigs.tests.factories import GigFactory, in_days
from apps.verification.constants import BadgeKind, CaseStatus
from apps.verification.models import Badge
from apps.verification.tests.factories import CaseFactory

pytestmark = pytest.mark.django_db


def staff(*roles: str):
    user = AdminUserFactory()
    for role in roles:
        user.groups.add(Group.objects.get(name=role))
    return user


def browser(user) -> Client:
    client = Client()
    client.force_login(user)
    return client


def audit(action: str):
    return AuditLog.objects.filter(action=action)


class TestRoles:
    def test_every_role_group_exists_with_exactly_its_permissions(self):
        sync_roles()
        for role, expected in PERMISSIONS.items():
            group = Group.objects.get(name=role)
            got = {
                f"{p.content_type.app_label}.{p.codename}"
                for p in group.permissions.select_related("content_type")
            }
            assert got == set(expected), role

    def test_each_role_can_do_only_its_job(self):
        can = {
            role: {
                "verify": staff(role).has_perm("backoffice.review_verification"),
                "gigs": staff(role).has_perm("backoffice.review_gigs"),
                "audit": staff(role).has_perm("backoffice.view_audit_log"),
                "roles": staff(role).has_perm("backoffice.manage_admin_roles"),
            }
            for role in AdminRole.values
        }
        assert can[AdminRole.SUPER_ADMIN] == dict.fromkeys(can[AdminRole.SUPER_ADMIN], True)
        assert can[AdminRole.TRUST] == {
            "verify": True,
            "gigs": False,
            "audit": True,
            "roles": False,
        }
        assert can[AdminRole.OPS] == {"verify": False, "gigs": True, "audit": True, "roles": False}
        assert can[AdminRole.FINANCE] == {
            "verify": False,
            "gigs": False,
            "audit": True,
            "roles": False,
        }
        assert can[AdminRole.SUPPORT] == dict.fromkeys(can[AdminRole.SUPPORT], False)

    def test_sync_undoes_hand_edits(self):
        support = Group.objects.get(name=AdminRole.SUPPORT)
        support.permissions.clear()
        sync_roles()
        assert support.permissions.count() == len(PERMISSIONS[AdminRole.SUPPORT])

    def test_grant_and_remove_a_role_is_audited(self):
        user = AdminUserFactory(is_staff=False)
        call_command("grant_admin_role", user.phone, "trust", stdout=StringIO())
        user.refresh_from_db()
        assert roles_of(user) == ["trust"] and user.is_staff
        entry = audit("user.admin_role_granted").get()
        assert entry.after["roles"] == ["trust"] and entry.before["roles"] == []

        call_command("grant_admin_role", user.phone, "trust", "--remove", stdout=StringIO())
        assert roles_of(user) == []
        assert audit("user.admin_role_removed").count() == 1

    def test_vendor_and_talent_accounts_cant_become_admins(self):
        with pytest.raises(CommandError, match="separate account"):
            call_command("grant_admin_role", VendorFactory().phone, "ops", stdout=StringIO())


class TestVerificationQueue:
    def test_lists_waiting_cases_oldest_first_and_flags_overdue(self):
        now = timezone.now()
        old = CaseFactory(submitted_at=now - timedelta(days=3))
        new = CaseFactory(submitted_at=now - timedelta(hours=1))
        CaseFactory(status=CaseStatus.APPROVED, submitted_at=now)
        response = browser(staff("trust")).get("/admin/queues/verification/")
        assert response.status_code == 200
        rows = response.context["rows"]
        assert [r["case"].pk for r in rows] == [old.pk, new.pk]
        assert [r["overdue"] for r in rows] == [True, False]
        assert b"Overdue" in response.content

    def test_filters_by_status_and_check(self):
        CaseFactory(status=CaseStatus.APPROVED, submitted_at=timezone.now())
        response = browser(staff("trust")).get(
            "/admin/queues/verification/", {"status": "approved", "check": "id_selfie"}
        )
        assert len(response.context["rows"]) == 1

    def test_only_roles_that_review_get_in(self):
        assert browser(staff("ops")).get("/admin/queues/verification/").status_code == 403
        assert browser(staff("support")).get("/admin/queues/verification/").status_code == 403
        anonymous = Client().get("/admin/queues/verification/")
        assert anonymous.status_code == 302 and "/admin/login/" in anonymous["Location"]

    def test_approve_needs_a_reason_then_grants_the_badge_and_audits(self):
        case = CaseFactory(submitted_at=timezone.now())
        reviewer = staff("trust")
        client = browser(reviewer)
        url = f"/admin/queues/verification/{case.pk}/"

        page = client.post(url, {"decision": "approve", "reason": " "})
        assert page.status_code == 200
        assert "Give a reason" in page.content.decode()
        case.refresh_from_db()
        assert case.status == CaseStatus.SUBMITTED

        done = client.post(url, {"decision": "approve", "reason": "Name and photo match."})
        assert done.status_code == 302
        case.refresh_from_db()
        assert case.status == CaseStatus.APPROVED and case.reviewer == reviewer
        assert Badge.objects.filter(user=case.user, kind=BadgeKind.ID_VERIFIED).exists()
        entry = audit("verification.case.approved").get()
        assert entry.actor == reviewer and entry.after["reason"] == "Name and photo match."
        # The page after the decision shows it in the case's history.
        after = client.get(done["Location"])
        assert after.status_code == 200
        assert "verification.case.approved" in after.content.decode()
        assert "Name and photo match." in after.content.decode()

    @pytest.mark.parametrize(
        ("decision", "status"),
        [("reject", CaseStatus.REJECTED), ("request_changes", CaseStatus.CHANGES_REQUESTED)],
    )
    def test_reject_and_request_changes(self, decision, status):
        case = CaseFactory(submitted_at=timezone.now())
        client = browser(staff("trust"))
        assert (
            client.post(
                f"/admin/queues/verification/{case.pk}/", {"decision": decision}
            ).status_code
            == 200
        )
        client.post(
            f"/admin/queues/verification/{case.pk}/",
            {"decision": decision, "reason": "Photo is blurry."},
        )
        case.refresh_from_db()
        assert case.status == status and case.reason == "Photo is blurry."
        assert audit(f"verification.case.{status}").count() == 1

    def test_detail_shows_the_case_and_its_history(self):
        case = CaseFactory(submitted_at=timezone.now(), details={"document": "Aadhaar ending 1234"})
        page = browser(staff("trust")).get(f"/admin/queues/verification/{case.pk}/")
        assert page.status_code == 200
        body = page.content.decode()
        assert "Aadhaar ending 1234" in body and "Approve" in body and "Reject" in body


class TestGigQueue:
    def test_lists_gigs_in_review_with_their_rule_breaks(self):
        ok = GigFactory(status=GigStatus.IN_REVIEW, submitted_at=timezone.now() - timedelta(days=1))
        bad = GigFactory(status=GigStatus.IN_REVIEW, submitted_at=timezone.now())
        Gig.objects.filter(pk=bad.pk).update(start_date=in_days(-1), apply_by=in_days(-3))
        GigFactory(status=GigStatus.DRAFT)
        response = browser(staff("ops")).get("/admin/queues/gigs/")
        assert response.status_code == 200
        rows = response.context["rows"]
        assert [r["gig"].pk for r in rows] == [ok.pk, bad.pk]
        assert [r["report"].breaks for r in rows] == [0, 1]
        flagged = browser(staff("ops")).get("/admin/queues/gigs/", {"flagged": "1"})
        assert [r["gig"].pk for r in flagged.context["rows"]] == [bad.pk]

    def test_rule_report_explains_the_break(self):
        gig = GigFactory(status=GigStatus.IN_REVIEW)
        Gig.objects.filter(pk=gig.pk).update(start_date=in_days(-1), apply_by=in_days(-3))
        gig.refresh_from_db()
        report = gig_rules(gig)
        dates = next(r for r in report.rows if "Starts in the future" in r.rule)
        assert dates.broken
        assert "The start date must be in the future." in dates.problems
        hours = next(r for r in report.rows if "hours a day" in r.rule)
        assert not hours.broken and hours.value == str(gig.hours_per_day)
        assert "The host hasn't verified their ID." in report.warnings

    def test_approve_puts_it_live_and_audits(self):
        gig = GigFactory(status=GigStatus.IN_REVIEW, submitted_at=timezone.now())
        reviewer = staff("ops")
        assert (
            browser(reviewer)
            .post(f"/admin/queues/gigs/{gig.pk}/", {"decision": "approve"})
            .status_code
            == 302
        )
        gig.refresh_from_db()
        assert gig.status == GigStatus.LIVE
        entry = audit("gig.live").get()
        assert entry.actor == reviewer and entry.after["by"] == "admin"

    def test_a_gig_that_breaks_a_rule_cant_be_approved(self):
        gig = GigFactory(status=GigStatus.IN_REVIEW)
        Gig.objects.filter(pk=gig.pk).update(start_date=in_days(-1), apply_by=in_days(-3))
        page = browser(staff("ops")).post(f"/admin/queues/gigs/{gig.pk}/", {"decision": "approve"})
        assert page.status_code == 200
        assert "The start date must be in the future." in page.content.decode()
        gig.refresh_from_db()
        assert gig.status == GigStatus.IN_REVIEW

    def test_send_back_needs_a_note(self):
        gig = GigFactory(status=GigStatus.IN_REVIEW)
        client = browser(staff("ops"))
        assert (
            client.post(f"/admin/queues/gigs/{gig.pk}/", {"decision": "send_back"}).status_code
            == 200
        )
        client.post(
            f"/admin/queues/gigs/{gig.pk}/", {"decision": "send_back", "reason": "Add the meals."}
        )
        gig.refresh_from_db()
        assert gig.status == GigStatus.DRAFT and gig.status_reason == "Add the meals."
        assert audit("gig.draft").count() == 1
        history = client.get(f"/admin/queues/gigs/{gig.pk}/")
        assert history.status_code == 200 and "Add the meals." in history.content.decode()

    def test_trust_and_support_cant_approve_gigs(self):
        gig = GigFactory(status=GigStatus.IN_REVIEW)
        for role in ("trust", "support", "finance"):
            client = browser(staff(role))
            assert client.get("/admin/queues/gigs/").status_code == 403
            assert (
                client.post(f"/admin/queues/gigs/{gig.pk}/", {"decision": "approve"}).status_code
                == 403
            )


class TestAuditLogViewer:
    def test_readable_by_audit_roles_and_read_only(self):
        entry = AuditLog.objects.create(action="gig.live", object_type="gigs.gig", object_id="1")
        client = browser(staff("finance"))
        listing = client.get("/admin/common/auditlog/")
        assert listing.status_code == 200 and b"gig.live" in listing.content
        detail = client.get(f"/admin/common/auditlog/{entry.pk}/change/")
        assert detail.status_code == 200 and b'name="_save"' not in detail.content
        assert client.post(f"/admin/common/auditlog/{entry.pk}/delete/").status_code == 403
        assert browser(staff("support")).get("/admin/common/auditlog/").status_code == 403

    def test_filters(self):
        admin_user = AdminUserFactory()
        AuditLog.objects.create(
            action="gig.live", object_type="gigs.gig", object_id="1", actor=admin_user
        )
        AuditLog.objects.create(
            action="verification.case.approved", object_type="v.c", object_id="2"
        )
        client = browser(staff("trust"))
        by_area = client.get("/admin/common/auditlog/", {"area": "verification"})
        assert [e.action for e in by_area.context["cl"].result_list] == [
            "verification.case.approved"
        ]
        by_who = client.get("/admin/common/auditlog/", {"who": "admin"})
        assert [e.action for e in by_who.context["cl"].result_list] == ["gig.live"]
        by_phone = client.get("/admin/common/auditlog/", {"q": admin_user.phone})
        assert len(by_phone.context["cl"].result_list) == 1


class TestEveryAdminActionIsAudited:
    def test_a_change_in_the_django_admin_writes_an_audit_row(self):
        superuser = AdminUserFactory(is_superuser=True)
        target = TalentFactory()
        client = browser(superuser)
        response = client.post(
            f"/admin/accounts/user/{target.pk}/change/",
            {
                "phone": target.phone,
                "email": "",
                "role": "talent",
                "is_active": "",  # deactivate
                "groups": [],
                "user_permissions": [],
            },
        )
        assert response.status_code == 302, response.content[:500]
        entry = audit("admin.changed").get()
        assert entry.actor == superuser and entry.object_type == "accounts.user"
        assert entry.object_id == str(target.pk)
        assert audit("user.updated").get().after == {"is_active": False}

    def test_changing_someones_admin_groups_is_audited(self):
        superuser = AdminUserFactory(is_superuser=True)
        target = staff("support")
        browser(superuser).post(
            f"/admin/accounts/user/{target.pk}/change/",
            {
                "phone": target.phone,
                "email": "",
                "role": "admin",
                "is_active": "on",
                "is_staff": "on",
                "groups": [Group.objects.get(name="trust").pk],
                "user_permissions": [],
            },
        )
        entry = audit("user.admin_roles_changed").get()
        assert entry.before == {"groups": ["support"]} and entry.after == {"groups": ["trust"]}


def test_the_admin_index_links_only_the_queues_a_role_can_use():
    page = browser(staff("ops")).get("/admin/")
    assert page.status_code == 200
    body = page.content.decode()
    assert "Gig approval queue" in body and "Audit log" in body
    assert "Verification queue" not in body
