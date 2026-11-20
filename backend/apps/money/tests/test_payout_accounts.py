"""Linking a payout account: shape checks, masking, provider validation, the change hold."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import TalentFactory
from apps.common.models import AuditLog
from apps.money import payout_accounts
from apps.money.gateway.base import GatewayError
from apps.money.gateway.fake import FakePayoutProvider
from apps.money.gateway.payouts import Validation
from apps.money.models import PayoutAccount
from apps.money.payout_accounts import PayoutAccountError, link
from apps.money.tests.helpers import deliver_x
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db
BANK = {"account_number": "1234 5678 9012", "ifsc": "hdfc0001234", "holder_name": " Asha  Rao "}


class TestShape:
    @pytest.mark.parametrize("vpa", ["asha@okicici", "asha.rao-1@ybl", "98765@paytm"])
    def test_good_upi_ids(self, vpa):
        assert payout_accounts.clean("upi", vpa=vpa)[0] == vpa.lower()

    @pytest.mark.parametrize("vpa", ["", "asha", "@okicici", "asha@", "as ha@ok", "a@1bank"])
    def test_bad_upi_ids(self, vpa):
        with pytest.raises(PayoutAccountError, match="UPI id"):
            payout_accounts.clean("upi", vpa=vpa)

    @pytest.mark.parametrize(
        ("details", "message"),
        [
            ({**BANK, "account_number": "12345"}, "9 to 18 digits"),
            ({**BANK, "account_number": "12345678x01"}, "9 to 18 digits"),
            ({**BANK, "ifsc": "HDFC1001234"}, "IFSC"),
            ({**BANK, "holder_name": " "}, "name on the account"),
        ],
    )
    def test_bad_bank_details(self, details, message):
        with pytest.raises(PayoutAccountError, match=message):
            payout_accounts.clean("bank", **details)

    def test_an_unknown_method(self):
        with pytest.raises(PayoutAccountError, match="UPI or a bank"):
            payout_accounts.clean("cash")

    def test_only_masked_values_are_kept(self):
        assert payout_accounts.clean("upi", vpa="Asha.Rao@OkIcici")[2] == "as•••@okicici"
        vpa, bank, display = payout_accounts.clean("bank", **BANK)
        assert (vpa, display) == ("", "HDFC0001234 ••••9012")
        assert (bank.account_number, bank.ifsc, bank.holder_name) == (
            "123456789012",
            "HDFC0001234",
            "Asha Rao",
        )


class TestLinking:
    def test_linking_creates_a_fund_account_and_starts_validation(self):
        talent = TalentFactory()
        account = link(talent, method="bank", **BANK)
        assert account.validation_status == "pending" and not account.active
        assert account.display == "HDFC0001234 ••••9012" and account.hold_until is None
        assert [c[0] for c in FakePayoutProvider.calls] == ["contact", "fund_account", "validate"]
        # The full account number went to the provider and nowhere else.
        stored = PayoutAccount.objects.filter(pk=account.pk).values().get()
        assert not any("123456789012" in str(v) for v in stored.values())
        assert not AuditLog.objects.filter(after__icontains="123456789012").exists()
        assert AuditLog.objects.filter(action="money.payout_account_linked").count() == 1

    def test_the_validation_webhook_verifies_it(self):
        account = link(TalentFactory(), method="upi", vpa="asha@okicici")
        outcome = deliver_x(
            "fund_account.validation.completed",
            "fund_account.validation",
            {
                "id": account.validation_id,
                "status": "completed",
                "results": {"account_status": "active"},
            },
        )
        account.refresh_from_db()
        assert outcome == "payout account verified"
        assert account.active and account.validation_status == "verified" and account.verified_at

    def test_an_inactive_account_fails_validation_and_says_so(self):
        account = link(TalentFactory(), method="bank", **BANK)
        deliver_x(
            "fund_account.validation.completed",
            "fund_account.validation",
            {
                "id": account.validation_id,
                "status": "completed",
                "results": {"account_status": "invalid"},
            },
        )
        account.refresh_from_db()
        assert account.validation_status == "failed" and not account.active
        assert "isn't active" in account.validation_reason
        assert Notification.objects.filter(
            user=account.talent, kind="money.payout_account_failed"
        ).exists()

    def test_a_stale_validation_result_is_ignored(self):
        talent = TalentFactory()
        first = link(talent, method="upi", vpa="asha@okicici")
        old_id = first.validation_id
        link(talent, method="upi", vpa="asha2@okicici")
        assert (
            deliver_x(
                "fund_account.validation.completed",
                "fund_account.validation",
                {"id": old_id, "status": "completed", "results": {"account_status": "active"}},
            )
            == "not a current payout account"
        )

    def test_the_sync_job_asks_about_pending_validations(self):
        account = link(TalentFactory(), method="upi", vpa="asha@okicici")
        FakePayoutProvider.validations[account.validation_id] = Validation(
            account.validation_id, "verified"
        )
        later = timezone.now() + timedelta(minutes=10)
        assert payout_accounts.sync_pending(later) == {"validations_settled": 1}
        account.refresh_from_db()
        assert account.active

    def test_an_immediate_result_is_applied(self):
        FakePayoutProvider.validate_as = "verified"
        account = link(TalentFactory(), method="upi", vpa="asha@okicici")
        assert account.active and account.validation_status == "verified"

    def test_a_provider_error_saves_nothing(self):
        talent = TalentFactory()
        FakePayoutProvider.fail_next.append(GatewayError("down"))
        with pytest.raises(PayoutAccountError) as caught:
            link(talent, method="upi", vpa="asha@okicici")
        assert caught.value.status == 502
        assert not PayoutAccount.objects.filter(talent=talent).exists()


class TestChanging:
    def test_a_change_holds_payouts_for_a_day_and_tells_the_talent(
        self, django_capture_on_commit_callbacks
    ):
        talent = TalentFactory()
        FakePayoutProvider.validate_as = "verified"
        first = link(talent, method="upi", vpa="asha@okicici")
        now = timezone.now()
        with django_capture_on_commit_callbacks(execute=True):
            changed = link(talent, method="bank", now=now, **BANK)
        assert changed.pk == first.pk and changed.provider_contact_id == first.provider_contact_id
        assert changed.hold_until == now + timedelta(hours=24) and changed.changed_at == now
        assert ("deactivate", first.fund_account_id) in FakePayoutProvider.calls
        note = Notification.objects.get(user=talent, kind="money.payout_account_changed")
        assert "HDFC0001234 ••••9012" in note.body and note.urgent
        entry = AuditLog.objects.get(action="money.payout_account_changed")
        assert entry.before["display"] == "as•••@okicici"
        assert entry.after["display"] == "HDFC0001234 ••••9012"

    def test_the_change_alert_cant_be_switched_off(self):
        from apps.notifications import catalog

        overrides = {("security", c): False for c in catalog.ALL_CHANNELS}
        on = catalog.enabled_channels("money.payout_account_changed", overrides)
        assert {"push", "email", "sms", "in_app"} <= on
