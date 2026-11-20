"""Payout runs: the rules that hold payouts back, retries, idempotency and webhooks."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.tests.factories import AdminUserFactory
from apps.common.models import AuditLog
from apps.money import deliverables, ledger, payouts
from apps.money.gateway.base import GatewayError
from apps.money.gateway.fake import FakePayoutProvider
from apps.money.gateway.payouts import ProviderPayout
from apps.money.ledger import TALENT
from apps.money.models import (
    Escrow,
    EscrowStatus,
    Payout,
    PayoutRun,
    PayoutStatus,
    PayoutTrigger,
)
from apps.money.models import PayoutAttemptStatus as A
from apps.money.tests.helpers import (
    check_in,
    deliver_x,
    funded,
    payout_account,
    retry_payouts,
    send_payout,
)
from apps.notifications.models import Notification
from apps.verification.models import Badge

pytestmark = pytest.mark.django_db


def released(*, account=True):
    """A released escrow whose payout hasn't been attempted yet."""
    booking, record = funded()
    if account:
        payout_account(booking.talent)
    check_in(booking)
    submission = deliverables.submit(booking.pk, talent=booking.talent, note="Reels")
    deliverables.review(submission.pk, vendor=booking.vendor, approve=True)
    record.refresh_from_db()
    assert record.status == EscrowStatus.RELEASED and record.payout_status == ""
    return booking, record


def provider_payouts():
    return [c for c in FakePayoutProvider.calls if c[0] == "payout"]


class TestHolds:
    def test_no_verified_account_waits(self):
        booking, record = released(account=False)
        assert send_payout(record.pk).payout_status == PayoutStatus.WAITING_FOR_ACCOUNT
        payout_account(booking.talent, active=False)  # linked, validation pending
        assert send_payout(record.pk).payout_status == PayoutStatus.WAITING_FOR_ACCOUNT
        assert not provider_payouts()

    def test_the_first_payout_needs_a_verified_id(self):
        booking, record = released()
        Badge.objects.filter(user=booking.talent).update(
            revoked_at=timezone.now(), revoke_reason="Expired"
        )
        assert send_payout(record.pk).payout_status == PayoutStatus.ON_HOLD
        note = Notification.objects.get(user=booking.talent, kind="money.payout_on_hold")
        assert "Verify your ID" in note.body
        assert not provider_payouts()

    def test_later_payouts_dont_need_the_id_again(self):
        booking, record = released()
        payout = send_payout(record.pk).payouts.get()
        payouts.accept(payout.pk, provider_id=payout.provider_payout_id, processed=True)
        Badge.objects.filter(user=booking.talent).update(
            revoked_at=timezone.now(), revoke_reason="Expired"
        )
        assert (
            payouts.hold_reason(booking.talent_id, booking.talent.payout_account, timezone.now())
            is None
        )

    def test_a_changed_account_holds_payouts_for_24_hours(self):
        booking, record = released()
        account = booking.talent.payout_account
        account.hold_until = timezone.now() + timedelta(hours=24)
        account.save()
        assert send_payout(record.pk).payout_status == PayoutStatus.ON_HOLD
        assert send_payout(record.pk, now=timezone.now() + timedelta(hours=25)).payout_status == (
            PayoutStatus.SENT
        )

    def test_the_kill_switch_pauses_payouts(self, settings):
        _, record = released()
        settings.ESCROW_PAUSED = True
        assert send_payout(record.pk).payout_status == PayoutStatus.PAUSED
        settings.ESCROW_PAUSED = False
        assert retry_payouts()["sent"] == 1


class TestAttempts:
    def test_a_payout_is_made_once(self):
        _, record = released()
        record = send_payout(record.pk)
        send_payout(record.pk)
        retry_payouts()
        assert len(provider_payouts()) == 1
        payout = record.payouts.get()
        assert (payout.attempt, payout.status) == (1, A.PROCESSING)
        assert ledger.balance(TALENT) == 0

    def test_the_database_allows_one_live_payout_per_escrow(self):
        _, record = released()
        payout = send_payout(record.pk).payouts.get()
        with pytest.raises(IntegrityError), transaction.atomic():
            Payout.objects.create(
                escrow=record,
                talent_id=payout.talent_id,
                attempt=2,
                amount_paise=1,
                fund_account_id="x",
                account_display="x",
            )

    def test_a_stuck_payout_is_resent_with_the_same_key(self):
        booking, record = released()
        # A crash after the attempt was committed, before the provider answered.
        Payout.objects.create(
            escrow=record,
            talent=booking.talent,
            attempt=1,
            amount_paise=record.payout_paise,
            fund_account_id=booking.talent.payout_account.fund_account_id,
            account_display="x",
            created_at=timezone.now() - timedelta(minutes=30),
        )
        Escrow.objects.filter(pk=record.pk).update(payout_status=PayoutStatus.SENDING)
        retry_payouts(hours_later=0)
        payout = record.payouts.get()
        assert payout.status == A.PROCESSING and len(provider_payouts()) == 1
        assert list(FakePayoutProvider.payouts_by_key) == [str(payout.pk)]

    def test_failures_back_off_then_wait_for_an_admin(self, settings):
        settings.ESCROW_ALERT_EMAILS = []
        _, record = released()
        for _ in range(5):
            FakePayoutProvider.fail_next.append(GatewayError("Beneficiary bank down"))
        start = timezone.now()
        send_payout(record.pk, now=start)
        first = record.payouts.get()
        assert first.status == A.FAILED and first.failure_reason.endswith("Beneficiary bank down")
        assert first.next_attempt_at == start + timedelta(minutes=15)
        assert send_payout(record.pk, now=start + timedelta(minutes=5)).payouts.count() == 1
        moment = start
        for gap in (
            timedelta(minutes=15),
            timedelta(hours=1),
            timedelta(hours=4),
            timedelta(hours=12),
        ):
            moment += gap
            send_payout(record.pk, now=moment)
        last = record.payouts.order_by("-attempt").first()
        assert last.attempt == 5 and last.next_attempt_at is None
        assert AuditLog.objects.filter(action="money.alert").exists()
        assert send_payout(record.pk, now=moment + timedelta(days=3)).payouts.count() == 5
        assert ledger.balance(TALENT) == record.payout_paise  # still owed
        assert Notification.objects.filter(kind="money.payout_failed").count() == 5

    def test_an_admin_retries_with_a_note(self):
        _, record = released()
        FakePayoutProvider.fail_next.append(GatewayError("down"))
        failed = send_payout(record.pk).payouts.get()
        with pytest.raises(payouts.PayoutError, match="Say why"):
            payouts.retry(failed.pk, admin=AdminUserFactory(), note=" ")
        run = payouts.retry(failed.pk, admin=AdminUserFactory(), note="Bank back up")
        assert run.trigger == PayoutTrigger.ADMIN and run.sent == 1
        assert AuditLog.objects.get(action="money.payout_retry").after["note"] == "Bank back up"
        with pytest.raises(payouts.PayoutError, match="latest failed"):
            payouts.retry(failed.pk, admin=AdminUserFactory(), note="again")

    def test_a_rejection_on_creation_is_a_failure(self, monkeypatch):
        _, record = released()
        monkeypatch.setattr(
            FakePayoutProvider,
            "create_payout",
            lambda self, **kw: ProviderPayout("pout_x", "rejected", reason="Invalid account"),
        )
        payout = send_payout(record.pk).payouts.get()
        assert payout.status == A.FAILED and payout.failure_reason == "Invalid account"
        assert ledger.balance(TALENT) == record.payout_paise


class TestWebhooks:
    def entity(self, payout, **extra):
        return {"id": payout.provider_payout_id, "reference_id": str(payout.pk), **extra}

    def test_processed_settles_and_tells_the_talent(self):
        booking, record = released()
        payout = send_payout(record.pk).payouts.get()
        assert deliver_x("payout.processed", "payout", self.entity(payout, utr="UTR9")) == (
            "payout processed"
        )
        payout.refresh_from_db()
        record.refresh_from_db()
        assert (payout.status, payout.utr) == (A.PROCESSED, "UTR9")
        assert (record.status, record.payout_status) == (
            EscrowStatus.PAID_OUT,
            PayoutStatus.SETTLED,
        )
        assert Notification.objects.filter(user=booking.talent, kind="money.payout_paid").exists()

    def test_a_reversal_undoes_a_settled_payout_and_it_is_retried(self):
        _, record = released()
        payout = send_payout(record.pk).payouts.get()
        deliver_x("payout.processed", "payout", self.entity(payout))
        reason = {"status_details": {"description": "Account closed"}}
        assert deliver_x("payout.reversed", "payout", self.entity(payout, **reason)) == (
            "payout reversed"
        )
        payout.refresh_from_db()
        record.refresh_from_db()
        assert payout.status == A.REVERSED and payout.failure_reason == "Account closed"
        assert (record.status, record.payout_status) == (EscrowStatus.RELEASED, PayoutStatus.FAILED)
        assert ledger.balance(TALENT) == record.payout_paise and ledger.is_balanced()
        retry_payouts()
        assert record.payouts.filter(status=A.PROCESSING).count() == 1

    def test_events_are_applied_once(self):
        _, record = released()
        payout = send_payout(record.pk).payouts.get()
        assert deliver_x("payout.failed", "payout", self.entity(payout), event_id="e1") == (
            "payout failed"
        )
        assert deliver_x("payout.failed", "payout", self.entity(payout), event_id="e1") == (
            "duplicate"
        )
        assert deliver_x("payout.failed", "payout", self.entity(payout), event_id="e2") == (
            "payout failed"
        )  # a repeat with a new id changes nothing either
        kinds = list(ledger.LedgerTransaction.objects.values_list("kind", flat=True))
        assert kinds.count("payout_reversed") == 1

    def test_unknown_payouts_and_events(self):
        assert deliver_x("payout.processed", "payout", {"id": "pout_other"}) == (
            "not a Barterly payout"
        )
        _, record = released()
        payout = send_payout(record.pk).payouts.get()
        assert deliver_x("payout.queued", "payout", self.entity(payout)) == "ignored"

    def test_a_bad_signature_is_refused(self):
        from apps.money.gateway.fake import signed_x

        body, headers = signed_x({"event": "payout.processed"}, "wrong", "e1")
        with pytest.raises(GatewayError, match="signature"):
            payouts.handle_webhook(body, headers)


class TestRuns:
    def test_a_run_counts_what_it_sent_and_held(self):
        _, sent = released()
        released(account=False)
        run = payouts.run(PayoutTrigger.SCHEDULED)
        assert (run.considered, run.sent, run.held, run.failed) == (2, 1, 1, 0)
        assert run.sent_paise == sent.payout_paise
        assert run.held_reasons == {"no_verified_account": 1}
        assert run.finished_at is not None

    def test_release_starts_a_run_for_that_escrow(self, django_capture_on_commit_callbacks):
        booking, _ = funded()
        payout_account(booking.talent)
        check_in(booking)
        submission = deliverables.submit(booking.pk, talent=booking.talent, note="Reels")
        with django_capture_on_commit_callbacks(execute=True):
            deliverables.review(submission.pk, vendor=booking.vendor, approve=True)
        run = PayoutRun.objects.get()
        assert run.trigger == PayoutTrigger.RELEASE and run.sent == 1

    def test_on_demand_is_rate_limited(self):
        booking, _ = released()
        run = payouts.request_payout(booking.talent)
        assert run.trigger == PayoutTrigger.ON_DEMAND and run.sent == 1
        with pytest.raises(payouts.PayoutError) as caught:
            payouts.request_payout(booking.talent)
        assert caught.value.status == 429
