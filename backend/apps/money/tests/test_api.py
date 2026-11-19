"""The money API: who can see and do what."""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.backoffice.roles import AdminRole, sync_roles
from apps.money.gateway.fake import signed
from apps.money.models import EscrowStatus
from apps.money.tests.helpers import TOTAL, check_in, funded, paid_booking, payout_account
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def finance():
    sync_roles()
    user = AdminUserFactory()
    user.groups.add(Group.objects.get(name=AdminRole.FINANCE))
    return user


class TestEscrowAndFunding:
    def test_both_sides_see_the_escrow_and_the_quote(self):
        booking = paid_booking()
        for user in (booking.vendor, booking.talent):
            body = client_for(user).get(reverse("money:escrow", args=[booking.pk])).json()
            assert body["needs_escrow"] is True and body["escrow"] is None
            assert body["quote"]["total_paise"] == TOTAL and body["paused"] is False

    def test_strangers_get_a_404(self):
        booking = paid_booking()
        response = client_for(TalentFactory()).get(reverse("money:escrow", args=[booking.pk]))
        assert response.status_code == 404

    def test_the_host_funds_and_gets_checkout_details(self, settings):
        settings.RAZORPAY_KEY_ID = "rzp_test_public"
        booking = paid_booking()
        url = reverse("money:fund", args=[booking.pk])
        assert client_for(booking.talent).post(url).status_code == 403
        assert client_for(VendorFactory()).post(url).status_code == 404
        body = client_for(booking.vendor).post(url).json()
        assert body["amount_paise"] == TOTAL and body["key_id"] == "rzp_test_public"
        assert body["escrow"]["status"] == EscrowStatus.FUNDING

    def test_funding_while_paused_is_a_503(self, settings):
        settings.ESCROW_PAUSED = True
        booking = paid_booking()
        response = client_for(booking.vendor).post(reverse("money:fund", args=[booking.pk]))
        assert response.status_code == 503


class TestDeliverablesApi:
    def test_hand_in_and_approve(self):
        booking, _ = funded()
        payout_account(booking.talent)
        check_in(booking)
        url = reverse("money:deliverables", args=[booking.pk])
        assert client_for(booking.vendor).post(url, {"note": "x"}, format="json").status_code == 403
        bad = client_for(booking.talent).post(url, {"links": ["not a url"]}, format="json")
        assert bad.status_code == 400
        created = client_for(booking.talent).post(
            url, {"note": "Six reels", "links": ["https://instagram.com/p/1"]}, format="json"
        )
        assert created.status_code == 201
        listed = client_for(booking.vendor).get(url).json()
        assert [s["id"] for s in listed] == [created.json()["id"]]
        review = client_for(booking.vendor).post(
            reverse("money:review", args=[created.json()["id"]]), {"approve": True}, format="json"
        )
        assert review.status_code == 200
        body = review.json()
        assert body["escrow"]["status"] == EscrowStatus.RELEASED
        assert body["release_held_back"] == ""

    def test_asking_for_changes_without_a_note_is_a_400(self):
        booking, _ = funded()
        check_in(booking)
        created = client_for(booking.talent).post(
            reverse("money:deliverables", args=[booking.pk]), {"note": "v1"}, format="json"
        )
        response = client_for(booking.vendor).post(
            reverse("money:review", args=[created.json()["id"]]), {"approve": False}, format="json"
        )
        assert response.status_code == 400


class TestAdminApi:
    def test_decisions_need_the_finance_permission(self):
        booking, _ = funded()
        check_in(booking)
        url = reverse("money:decide", args=[booking.pk])
        body = {"decision": "refund", "note": "Host cancelled the work"}
        assert client_for(AdminUserFactory()).post(url, body, format="json").status_code == 403
        assert client_for(booking.vendor).post(url, body, format="json").status_code == 403
        response = client_for(finance()).post(url, body, format="json")
        assert response.status_code == 200 and response.json()["status"] == EscrowStatus.REFUNDED

    def test_the_kill_switch(self):
        url = reverse("money:kill-switch")
        user = finance()
        assert client_for(AdminUserFactory()).get(url).status_code == 403
        assert client_for(user).get(url).json()["paused"] is False
        no_reason = client_for(user).put(url, {"paused": True}, format="json")
        assert no_reason.status_code == 400
        paused = client_for(user).put(url, {"paused": True, "reason": "Incident"}, format="json")
        assert paused.json()["paused"] is True
        booking = paid_booking()
        assert (
            client_for(booking.vendor)
            .get(reverse("money:escrow", args=[booking.pk]))
            .json()["paused"]
            is True
        )

    def test_reconciliation_runs_are_listed(self):
        from datetime import date

        from apps.money import reconciliation

        reconciliation.run(date(2026, 11, 18))
        body = client_for(finance()).get(reverse("money:reconciliation")).json()
        assert body[0]["day"] == "2026-11-18" and body[0]["ok"] is True


class TestWebhookEndpoint:
    def test_signed_events_are_applied_and_bad_ones_refused(self, client, settings):
        url = reverse("money:webhook")
        body, headers = signed({"event": "order.paid"}, "wrong", "evt_1")
        bad = client.post(
            url, body, content_type="application/json", headers={k: v for k, v in headers.items()}
        )
        assert bad.status_code == 400
        body, headers = signed(
            {"event": "order.paid"}, settings.RAZORPAY_ESCROW_WEBHOOK_SECRET, "evt_2"
        )
        good = client.post(url, body, content_type="application/json", headers=headers)
        assert good.status_code == 200 and good.json() == {"outcome": "ignored"}
