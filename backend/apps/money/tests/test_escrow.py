"""Escrow end to end: quote, funding, the check-in guard, release and its split, payouts,
refunds, disputes, auto-release and the kill switch."""

from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.tests.factories import AdminUserFactory
from apps.bookings.lifecycle import Actor, BookingStatus
from apps.bookings.services import BookingRefused, transition
from apps.bookings.tests.helpers import booked
from apps.common.models import AuditLog
from apps.gigs.constants import CompensationModel, StipendPeriod
from apps.money import deliverables, escrow, ledger
from apps.money.escrow import EscrowError
from apps.money.gateway.base import GatewayError
from apps.money.gateway.fake import FakeEscrowGateway, FakePayoutProvider
from apps.money.ledger import (
    COMMISSION,
    ESCROW,
    FEE_RECOVERY,
    GATEWAY,
    GATEWAY_FEES,
    GST_INPUT,
    GST_OUTPUT,
    TALENT,
    TDS,
)
from apps.money.models import (
    DeliverableSubmission,
    Escrow,
    EscrowControl,
    EscrowStatus,
    LedgerTransaction,
    PayoutStatus,
    SubmissionReview,
)
from apps.money.tests.helpers import (
    FEE,
    FEE_GST,
    GATEWAY_FEE,
    GATEWAY_FEE_TAX,
    STIPEND,
    TOTAL,
    capture,
    check_in,
    day_one,
    deliver,
    deliver_x,
    funded,
    paid_booking,
    payout_account,
    retry_payouts,
    send_payout,
)
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db
E = EscrowStatus
# Releasing ₹5,000 with PAN on file: 8% commission, 18% GST on it, 1% TDS.
COMMISSION_P, COMMISSION_GST_P, TDS_P = 40_000, 7_200, 5_000
PAYOUT = STIPEND - COMMISSION_P - COMMISSION_GST_P - TDS_P


def audit(action):
    return AuditLog.objects.filter(action=action)


def ready_to_release(*, account=True, pan=True):
    booking, record = funded()
    if account:
        payout_account(booking.talent, pan=pan)
    check_in(booking)
    return booking, record


def approve(booking, now=None):
    submission = deliverables.submit(
        booking.pk,
        talent=booking.talent,
        note="Six reels",
        links=["https://instagram.com/p/1"],
        now=now,
    )
    return deliverables.review(submission.pk, vendor=booking.vendor, approve=True, now=now)


class TestQuoteAndSplit:
    def test_the_host_pays_the_stipend_plus_the_fee_and_its_gst(self):
        booking = paid_booking()
        assert escrow.quote(booking) == {
            "stipend": STIPEND,
            "fee": FEE,
            "fee_gst": FEE_GST,
            "total": TOTAL,
        }

    @pytest.mark.parametrize(
        ("period", "amount", "expected"),
        [
            (StipendPeriod.TOTAL, "5000", 500_000),
            (StipendPeriod.PER_WEEK, "7000", 1_800_000),  # 18 days of ₹1,000 a day
            (StipendPeriod.PER_MONTH, "30000", 1_800_000),
            (StipendPeriod.PER_WEEK, "100", 25_714),
        ],  # 18/7 x ₹100, rounded half up
    )
    def test_weekly_and_monthly_stipends_are_prorated_by_day(self, period, amount, expected):
        terms = {
            "stipend_amount": amount,
            "stipend_period": period,
            "start_date": "2026-12-01",
            "end_date": "2026-12-19",
        }
        assert escrow.stipend_for(terms) == expected

    def test_a_stipend_needs_an_amount(self):
        with pytest.raises(EscrowError, match="no stipend"):
            escrow.stipend_for(
                {"stipend_amount": "", "start_date": "2026-12-01", "end_date": "2026-12-02"}
            )

    def test_the_release_splits_into_commission_gst_tds_and_payout(self, settings):
        assert escrow.split(STIPEND, pan_on_file=True) == {
            "commission": COMMISSION_P,
            "commission_gst": COMMISSION_GST_P,
            "tds": TDS_P,
            "payout": PAYOUT,
        }
        assert escrow.split(STIPEND, pan_on_file=False)["tds"] == 100_000  # 20% without PAN
        settings.ESCROW_TDS_ENABLED = False
        assert escrow.split(STIPEND, pan_on_file=True)["tds"] == 0
        settings.ESCROW_TDS_ENABLED = True
        settings.ESCROW_TDS_THRESHOLD_PAISE = STIPEND + 1
        assert escrow.split(STIPEND, pan_on_file=True)["tds"] == 0
        settings.ESCROW_COMMISSION_BPS = 1000
        assert escrow.split(STIPEND, pan_on_file=True)["commission"] == 50_000

    def test_every_split_adds_up_exactly(self):
        for amount in [*range(1, 400, 7), 99_999, 1_234_567, 10**12 + 3]:
            for pan in (True, False):
                try:
                    parts = escrow.split(amount, pan_on_file=pan)
                except EscrowError:
                    continue  # too small to leave the talent anything
                assert all(isinstance(v, int) and v >= 0 for v in parts.values())
                assert sum(parts.values()) == amount


class TestFunding:
    def test_the_host_starts_funding_with_a_gateway_order(self):
        booking = paid_booking()
        record, order_id = escrow.start_funding(booking.pk, vendor=booking.vendor)
        assert record.status == E.FUNDING and record.total_paise == TOTAL
        assert FakeEscrowGateway.calls == [("order", TOTAL, f"escrow-{booking.pk}")]
        assert audit("money.funding_started").count() == 1
        # Asking again before paying returns the same order.
        again, same = escrow.start_funding(booking.pk, vendor=booking.vendor)
        assert (again.pk, same) == (record.pk, order_id)
        assert len(FakeEscrowGateway.calls) == 1

    def test_only_the_bookings_host_can_fund_it(self):
        booking = paid_booking()
        with pytest.raises(escrow.Booking.DoesNotExist):
            escrow.start_funding(booking.pk, vendor=booking.talent)

    def test_volunteer_gigs_have_nothing_to_fund(self):
        booking = booked()
        with pytest.raises(EscrowError, match="no stipend"):
            escrow.start_funding(booking.pk, vendor=booking.vendor)

    def test_funding_waits_for_a_confirmed_booking(self):
        from apps.bookings.tests.helpers import accepted
        from apps.money.tests.helpers import live_gig

        booking = accepted(
            live_gig(
                compensation_model=CompensationModel.PAID,
                stipend_amount=5000,
                stipend_period="total",
                stay_type="none",
            )
        )
        with pytest.raises(EscrowError, match="once the booking is confirmed"):
            escrow.start_funding(booking.pk, vendor=booking.vendor)

    def test_a_gateway_failure_creates_nothing(self):
        booking = paid_booking()
        FakeEscrowGateway.fail_next.append(GatewayError("down"))
        with pytest.raises(EscrowError) as caught:
            escrow.start_funding(booking.pk, vendor=booking.vendor)
        assert caught.value.status == 502
        assert not Escrow.objects.exists()

    def test_the_capture_holds_the_money_and_balances_the_ledger(self):
        booking, record = funded()
        assert record.status == E.HELD and record.gateway_payment_id == "pay_1"
        assert ledger.balance(ESCROW) == STIPEND
        assert ledger.balance(FEE_RECOVERY) == FEE
        assert ledger.balance(GST_OUTPUT) == FEE_GST
        assert ledger.balance(GATEWAY_FEES) == GATEWAY_FEE - GATEWAY_FEE_TAX
        assert ledger.balance(GST_INPUT) == GATEWAY_FEE_TAX
        assert ledger.balance(GATEWAY) == TOTAL - GATEWAY_FEE
        assert ledger.is_balanced()
        assert audit("money.funded").count() == 1
        assert set(
            Notification.objects.filter(kind="money.funded").values_list("user_id", flat=True)
        ) == {booking.talent_id, booking.vendor_id}

    def test_paid_bookings_check_in_only_once_funded(self):
        booking = paid_booking()
        with pytest.raises(BookingRefused, match="fund the stipend"):
            transition(
                booking.pk,
                BookingStatus.CHECKED_IN,
                actor=Actor.VENDOR,
                user=booking.vendor,
                now=day_one(booking),
            )
        funded(booking)
        assert check_in(booking).status == BookingStatus.DELIVERING

    def test_volunteer_bookings_check_in_without_escrow(self):
        assert check_in(booked()).status == BookingStatus.DELIVERING

    def test_a_funded_booking_cant_be_funded_again(self):
        booking, _ = funded()
        with pytest.raises(EscrowError, match="already funded"):
            escrow.start_funding(booking.pk, vendor=booking.vendor)


class TestRelease:
    def test_approval_releases_and_pays_out(self, django_capture_on_commit_callbacks):
        booking, record = ready_to_release()
        with django_capture_on_commit_callbacks(execute=True):
            submission, record, held_back = approve(booking)
        record.refresh_from_db()
        assert held_back == "" and submission.review == SubmissionReview.APPROVED
        assert (record.status, record.released_by) == (E.RELEASED, "vendor")
        assert (
            record.commission_paise,
            record.commission_gst_paise,
            record.tds_paise,
            record.payout_paise,
        ) == (COMMISSION_P, COMMISSION_GST_P, TDS_P, PAYOUT)
        assert record.payout_status == PayoutStatus.SENT
        assert FakePayoutProvider.calls[-1] == (
            "payout",
            booking.talent.payout_account.fund_account_id,
            PAYOUT,
            "upi",
        )
        assert ledger.balance(ESCROW) == 0
        assert ledger.balance(COMMISSION) == COMMISSION_P
        assert ledger.balance(GST_OUTPUT) == FEE_GST + COMMISSION_GST_P
        assert ledger.balance(TDS) == TDS_P
        assert ledger.balance(TALENT) == 0
        assert ledger.is_balanced()
        assert audit("money.released").count() == 1 and audit("money.payout_sent").count() == 1
        assert Notification.objects.filter(kind="money.released", user=booking.talent).exists()
        # The bank confirms the payout.
        payout = record.payouts.get()
        assert (
            deliver_x(
                "payout.processed",
                "payout",
                {"id": payout.provider_payout_id, "reference_id": str(payout.pk), "utr": "UTR1"},
            )
            == "payout processed"
        )
        record.refresh_from_db()
        assert (record.status, record.payout_status) == (E.PAID_OUT, PayoutStatus.SETTLED)

    def test_without_pan_the_higher_tds_applies(self):
        booking, _ = ready_to_release(pan=False)
        _, record, _ = approve(booking)
        assert record.tds_paise == 100_000

    def test_money_isnt_released_before_the_stay_starts(self):
        booking, _ = funded()
        with pytest.raises(EscrowError, match="stay has started"):
            escrow.release(booking.pk, by="vendor")

    def test_the_database_refuses_an_overpaying_escrow(self):
        _, record = funded()
        with pytest.raises(IntegrityError), transaction.atomic():
            Escrow.objects.filter(pk=record.pk).update(released_paise=STIPEND + 1)

    def test_a_payout_waits_for_the_talents_account(self):
        booking, record = ready_to_release(account=False)
        approve(booking)
        record = send_payout(record.pk)
        assert record.payout_status == PayoutStatus.WAITING_FOR_ACCOUNT
        payout_account(booking.talent)
        assert retry_payouts()["sent"] == 1
        record.refresh_from_db()
        assert record.payout_status == PayoutStatus.SENT
        assert retry_payouts()["sent"] == 0  # sent once only
        assert ledger.balance(TALENT) == 0

    def test_a_gateway_error_marks_the_payout_failed_and_it_is_retried(self):
        booking, record = ready_to_release()
        approve(booking)
        FakePayoutProvider.fail_next.append(GatewayError("down"))
        assert send_payout(record.pk).payout_status == PayoutStatus.FAILED
        assert ledger.balance(TALENT) == PAYOUT  # nothing left the platform
        retry_payouts()
        record.refresh_from_db()
        assert record.payout_status == PayoutStatus.SENT and ledger.balance(TALENT) == 0

    def test_a_failed_payout_is_reversed_and_retried(self):
        booking, record = ready_to_release()
        approve(booking)
        record = send_payout(record.pk)
        first = record.payout_transfer_id
        assert deliver_x("payout.failed", "payout", {"id": first}) == "payout failed"
        assert ledger.balance(TALENT) == PAYOUT
        retry_payouts()
        record.refresh_from_db()
        assert record.payout_status == PayoutStatus.SENT and record.payout_transfer_id != first
        assert ledger.balance(TALENT) == 0 and ledger.is_balanced()


class TestDeliverables:
    def test_work_is_handed_in_after_check_in(self):
        booking, _ = funded()
        with pytest.raises(deliverables.DeliverableError, match="checked in"):
            deliverables.submit(booking.pk, talent=booking.talent, note="Early")
        check_in(booking)
        with pytest.raises(deliverables.DeliverableError, match="note or at least one link"):
            deliverables.submit(booking.pk, talent=booking.talent)
        with pytest.raises(escrow.Booking.DoesNotExist):
            deliverables.submit(booking.pk, talent=booking.vendor, note="Not mine")
        submission = deliverables.submit(booking.pk, talent=booking.talent, note="Reels")
        assert Notification.objects.filter(
            kind="money.deliverables_submitted", user=booking.vendor
        ).exists()
        assert audit("money.deliverables_submitted").count() == 1
        assert submission.review == SubmissionReview.PENDING

    def test_changes_need_a_note_and_only_the_latest_is_reviewed(self):
        booking, _ = ready_to_release()
        first = deliverables.submit(booking.pk, talent=booking.talent, note="v1")
        with pytest.raises(deliverables.DeliverableError, match="what needs to change"):
            deliverables.review(first.pk, vendor=booking.vendor, approve=False)
        deliverables.review(first.pk, vendor=booking.vendor, approve=False, note="More light")
        assert Notification.objects.filter(
            kind="money.changes_requested", user=booking.talent
        ).exists()
        with pytest.raises(deliverables.DeliverableError, match="already answered"):
            deliverables.review(first.pk, vendor=booking.vendor, approve=True)
        deliverables.submit(booking.pk, talent=booking.talent, note="v2")
        with pytest.raises(deliverables.DeliverableError, match="newer submission"):
            deliverables.review(first.pk, vendor=booking.vendor, approve=True)
        with pytest.raises(DeliverableSubmission.DoesNotExist):
            deliverables.review(first.pk, vendor=booking.talent, approve=True)


class TestAutoRelease:
    def test_an_unanswered_submission_releases_after_72_hours(self):
        booking, record = ready_to_release()
        submitted = day_one(booking)
        deliverables.submit(booking.pk, talent=booking.talent, note="Done", now=submitted)
        assert escrow.auto_release(submitted + timedelta(hours=71)) == {"released": 0}
        assert escrow.auto_release(submitted + timedelta(hours=72, minutes=1)) == {"released": 1}
        record.refresh_from_db()
        assert (record.status, record.released_by) == (E.RELEASED, "system")
        assert escrow.auto_release(submitted + timedelta(hours=80)) == {"released": 0}

    def test_asking_for_changes_stops_the_clock(self):
        booking, _ = ready_to_release()
        submitted = day_one(booking)
        submission = deliverables.submit(
            booking.pk, talent=booking.talent, note="v1", now=submitted
        )
        deliverables.review(submission.pk, vendor=booking.vendor, approve=False, note="Redo")
        assert escrow.auto_release(submitted + timedelta(days=10)) == {"released": 0}

    def test_no_submission_no_auto_release(self):
        booking, _ = ready_to_release()
        assert escrow.auto_release(day_one(booking) + timedelta(days=30)) == {"released": 0}


class TestKillSwitch:
    @pytest.fixture(params=["setting", "admin"])
    def pause(self, request, settings):
        def on():
            if request.param == "setting":
                settings.ESCROW_PAUSED = True
            else:
                escrow.set_paused(True, by=AdminUserFactory(), reason="Gateway incident")

        def off():
            settings.ESCROW_PAUSED = False
            EscrowControl.objects.filter(pk=1).update(paused=False)

        return on, off

    def test_paused_funding_is_refused(self, pause):
        on, _ = pause
        booking = paid_booking()
        on()
        with pytest.raises(EscrowError) as caught:
            escrow.start_funding(booking.pk, vendor=booking.vendor)
        assert caught.value.status == 503
        assert not FakeEscrowGateway.calls

    def test_paused_releases_wait_and_resume(self, pause):
        on, off = pause
        booking, record = ready_to_release()
        on()
        _, record, held_back = approve(booking)
        assert "paused" in held_back and record.status == E.HELD
        assert escrow.auto_release(day_one(booking)) == {"released": 0, "paused": 1}
        off()
        # The approval stands: the job releases it once resumed.
        assert escrow.auto_release(day_one(booking)) == {"released": 1}
        record.refresh_from_db()
        assert (record.status, record.released_by) == (E.RELEASED, "vendor")

    def test_paused_payouts_wait_and_resume(self, pause):
        on, off = pause
        booking, record = ready_to_release()
        approve(booking)
        on()
        assert send_payout(record.pk).payout_status == PayoutStatus.PAUSED
        off()
        retry_payouts()
        record.refresh_from_db()
        assert record.payout_status == PayoutStatus.SENT

    def test_webhooks_are_still_recorded_while_paused(self, settings):
        booking = paid_booking()
        record, _ = escrow.start_funding(booking.pk, vendor=booking.vendor)
        settings.ESCROW_PAUSED = True
        assert capture(record) == "held"

    def test_switching_is_audited(self):
        admin = AdminUserFactory()
        escrow.set_paused(True, by=admin, reason="Incident")
        assert escrow.paused()
        escrow.set_paused(False, by=admin)
        assert not escrow.paused()
        assert [e.after["paused"] for e in audit("money.kill_switch").order_by("id")] == [
            True,
            False,
        ]


class TestDisputesAndRefunds:
    def dispute(self, booking):
        transition(
            booking.pk,
            BookingStatus.DISPUTED,
            actor=Actor.TALENT,
            user=booking.talent,
            reason="Host left early",
            now=day_one(booking),
        )

    def test_a_dispute_freezes_release_until_an_admin_decides(self):
        booking, record = ready_to_release()
        submission = deliverables.submit(
            booking.pk, talent=booking.talent, note="Reels", now=day_one(booking)
        )
        self.dispute(booking)
        record.refresh_from_db()
        assert record.frozen and audit("money.frozen").count() == 1
        _, _, held_back = deliverables.review(submission.pk, vendor=booking.vendor, approve=True)
        assert "dispute" in held_back
        assert escrow.auto_release(day_one(booking) + timedelta(days=10)) == {"released": 0}
        record = escrow.decide(
            booking.pk, decision="release", admin=AdminUserFactory(), note="Work delivered"
        )
        assert (record.status, record.released_by, record.frozen) == (E.RELEASED, "admin", False)
        assert audit("money.admin_decision").count() == 1

    def test_an_admin_split_refunds_the_rest(self):
        booking, record = ready_to_release()
        self.dispute(booking)
        record = escrow.decide(
            booking.pk,
            decision="split",
            admin=AdminUserFactory(),
            talent_paise=300_000,
            note="Half the work",
        )
        assert record.status == E.SPLIT
        assert (record.released_paise, record.refund_paise) == (300_000, 200_000)
        assert ("refund", "pay_1", 200_000) in FakeEscrowGateway.calls
        # The refund is in the ledger when the gateway confirms it.
        assert ledger.balance(ESCROW) == 200_000
        assert (
            deliver(
                "refund.processed",
                "refund",
                {"id": record.refund_ids[0], "payment_id": "pay_1", "amount": 200_000},
            )
            == "refund recorded"
        )
        assert ledger.balance(ESCROW) == 0 and ledger.is_balanced()
        # The talent's share is paid out like any release.
        assert send_payout(record.pk).payout_status == PayoutStatus.SENT

    def test_an_admin_refund_returns_the_whole_stipend(self):
        booking, record = ready_to_release()
        record = escrow.decide(
            booking.pk, decision="refund", admin=AdminUserFactory(), note="No-show"
        )
        assert record.status == E.REFUNDED and record.refund_paise == STIPEND

    @pytest.mark.parametrize(
        ("kwargs", "message"),
        [
            ({"decision": "release", "note": " "}, "Say why"),
            ({"decision": "split", "note": "x"}, "talent's share"),
            ({"decision": "split", "note": "x", "talent_paise": STIPEND}, "talent's share"),
            ({"decision": "keep", "note": "x"}, "release, split or refund"),
        ],
    )
    def test_bad_decisions_are_refused_and_move_no_money(self, kwargs, message):
        booking, record = ready_to_release()
        with pytest.raises(EscrowError, match=message):
            escrow.decide(booking.pk, admin=AdminUserFactory(), **kwargs)
        assert not [c for c in FakeEscrowGateway.calls if c[0] == "refund"]
        record.refresh_from_db()
        assert record.status == E.HELD

    def test_cancelling_a_funded_booking_refunds_the_host(self):
        booking, record = funded()
        transition(
            booking.pk,
            BookingStatus.CANCELLED,
            actor=Actor.VENDOR,
            user=booking.vendor,
            reason="Closed for repairs",
        )
        record.refresh_from_db()
        assert record.status == E.REFUNDED and record.refund_paise == STIPEND
        assert FakeEscrowGateway.calls[-1] == ("refund", "pay_1", STIPEND)
        assert Notification.objects.filter(kind="money.refunded", user=booking.vendor).exists()

    def test_a_refund_that_cant_happen_doesnt_block_the_cancellation(self, settings):
        booking, record = funded()
        settings.ESCROW_PAUSED = True
        transition(
            booking.pk,
            BookingStatus.CANCELLED,
            actor=Actor.VENDOR,
            user=booking.vendor,
            reason="Closed",
        )
        booking.refresh_from_db()
        record.refresh_from_db()
        assert booking.status == BookingStatus.CANCELLED and record.status == E.HELD
        assert audit("money.refund_needed").count() == 1

    def test_a_payment_after_cancellation_is_refunded(self, django_capture_on_commit_callbacks):
        booking = paid_booking()
        record, _ = escrow.start_funding(booking.pk, vendor=booking.vendor)
        transition(
            booking.pk,
            BookingStatus.CANCELLED,
            actor=Actor.VENDOR,
            user=booking.vendor,
            reason="Changed plans",
        )
        with django_capture_on_commit_callbacks(execute=True):
            assert capture(record) == "held"
        record.refresh_from_db()
        assert record.status == E.REFUNDED

    def test_ledger_movements_are_never_duplicated(self):
        booking, record = ready_to_release()
        approve(booking)
        send_payout(record.pk)
        send_payout(record.pk)
        kinds = list(LedgerTransaction.objects.values_list("kind", flat=True).order_by("id"))
        assert kinds == ["escrow_funded", "escrow_released", "payout_sent"]
