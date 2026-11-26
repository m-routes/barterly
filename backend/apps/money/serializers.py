from rest_framework import serializers

from apps.money.escrow import DECISIONS
from apps.money.models import (
    DeliverableSubmission,
    Escrow,
    EscrowControl,
    Payout,
    PayoutAccount,
    PayoutMethod,
    PayoutRun,
    ReconciliationRun,
)


class EscrowSerializer(serializers.ModelSerializer):
    """All amounts are whole paise."""

    booking_id = serializers.UUIDField(read_only=True)
    unreleased_paise = serializers.IntegerField(read_only=True)

    class Meta:
        model = Escrow
        fields = [
            "id",
            "booking_id",
            "status",
            "stipend_paise",
            "fee_paise",
            "fee_gst_paise",
            "total_paise",
            "funded_at",
            "frozen",
            "released_paise",
            "commission_paise",
            "commission_gst_paise",
            "tds_paise",
            "payout_paise",
            "refund_paise",
            "unreleased_paise",
            "released_at",
            "released_by",
            "payout_status",
        ]
        read_only_fields = fields


class EscrowQuoteSerializer(serializers.Serializer):
    stipend_paise = serializers.IntegerField()
    fee_paise = serializers.IntegerField()
    fee_gst_paise = serializers.IntegerField()
    total_paise = serializers.IntegerField()


class EscrowOverviewSerializer(serializers.Serializer):
    needs_escrow = serializers.BooleanField()
    paused = serializers.BooleanField(help_text="The kill switch: no funding or payouts now.")
    escrow = EscrowSerializer(allow_null=True)
    quote = EscrowQuoteSerializer(allow_null=True, help_text="What funding would cost now.")


class EscrowCheckoutSerializer(serializers.Serializer):
    """Open the gateway's checkout with these."""

    escrow = EscrowSerializer()
    order_id = serializers.CharField()
    amount_paise = serializers.IntegerField()
    currency = serializers.CharField()
    key_id = serializers.CharField(help_text="The gateway's public key for checkout.")


class DeliverableSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliverableSubmission
        fields = ["id", "note", "links", "submitted_at", "review", "review_note", "reviewed_at"]
        read_only_fields = ["id", "submitted_at", "review", "review_note", "reviewed_at"]


class SubmitDeliverableSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
    links = serializers.ListField(
        child=serializers.URLField(max_length=500), max_length=20, required=False, default=list
    )


class ReviewDeliverableSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class ReviewResultSerializer(serializers.Serializer):
    submission = DeliverableSubmissionSerializer()
    escrow = EscrowSerializer(allow_null=True)
    release_held_back = serializers.CharField(
        help_text="Why the money wasn't released just now (it will be retried), or empty."
    )


class EscrowDecisionSerializer(serializers.Serializer):
    decision = serializers.ChoiceField(choices=DECISIONS)
    talent_paise = serializers.IntegerField(
        required=False, min_value=1, help_text="For a split: the talent's share, in paise."
    )
    note = serializers.CharField(max_length=1000)


class KillSwitchSerializer(serializers.ModelSerializer):
    paused_by_setting = serializers.SerializerMethodField()

    class Meta:
        model = EscrowControl
        fields = ["paused", "reason", "changed_at", "paused_by_setting"]
        read_only_fields = ["changed_at", "paused_by_setting"]

    def get_paused_by_setting(self, obj) -> bool:
        from django.conf import settings

        return bool(settings.ESCROW_PAUSED)


class ReconciliationRunSerializer(serializers.ModelSerializer):
    ledger = serializers.DictField(child=serializers.IntegerField())
    gateway = serializers.DictField(child=serializers.IntegerField())
    mismatches = serializers.ListField(child=serializers.DictField())

    class Meta:
        model = ReconciliationRun
        fields = ["day", "ok", "ledger", "gateway", "mismatches", "created_at"]
        read_only_fields = fields


# ---------- Payouts ----------


class PayoutAccountSerializer(serializers.ModelSerializer):
    """Masked: the full UPI id or account number is never stored or returned."""

    class Meta:
        model = PayoutAccount
        fields = [
            "method",
            "display",
            "validation_status",
            "validation_reason",
            "verified_at",
            "changed_at",
            "hold_until",
            "pan_on_file",
        ]
        read_only_fields = fields


class LinkPayoutAccountSerializer(serializers.Serializer):
    method = serializers.ChoiceField(choices=PayoutMethod.choices)
    vpa = serializers.CharField(
        max_length=256,
        required=False,
        default="",
        write_only=True,
        help_text="UPI id, for method upi.",
    )
    account_number = serializers.CharField(
        max_length=24, required=False, default="", write_only=True
    )
    ifsc = serializers.CharField(max_length=11, required=False, default="")
    holder_name = serializers.CharField(max_length=100, required=False, default="")


class WalletSerializer(serializers.Serializer):
    pending_paise = serializers.IntegerField(help_text="Held in escrow, not yet released.")
    pending_net_estimate_paise = serializers.IntegerField(
        help_text="Roughly what pending would pay you, after commission, GST and TDS."
    )
    available_paise = serializers.IntegerField(help_text="Released to you, not yet paid out.")
    in_transit_paise = serializers.IntegerField()
    paid_out_paise = serializers.IntegerField()
    tds_this_year_paise = serializers.IntegerField()
    financial_year = serializers.CharField()
    payout_account = PayoutAccountSerializer(allow_null=True)
    on_hold_reason = serializers.CharField(help_text="Why payouts wait, as a code; or empty.")
    on_hold_message = serializers.CharField()
    can_request_payout = serializers.BooleanField()


class WalletEntrySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["release", "payout"])
    at = serializers.DateTimeField()
    amount_paise = serializers.IntegerField(help_text="Release: your net; payout: the amount.")
    status = serializers.CharField()
    booking_id = serializers.UUIDField()
    gig_title = serializers.CharField()
    gross_paise = serializers.IntegerField()
    commission_paise = serializers.IntegerField()
    commission_gst_paise = serializers.IntegerField()
    tds_paise = serializers.IntegerField()
    account = serializers.CharField()
    reference = serializers.CharField()
    failure_reason = serializers.CharField()


class WalletHistoryQuerySerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["release", "payout"], required=False, default="")
    status = serializers.CharField(required=False, default="", max_length=30)
    start = serializers.DateField(required=False, default=None, help_text="From (India date).")
    end = serializers.DateField(required=False, default=None, help_text="To (India date).")
    fy = serializers.RegexField(
        r"^\d{4}-\d{2}$", required=False, default="", help_text="Financial year, like 2026-27."
    )


class StatementRowSerializer(serializers.Serializer):
    date = serializers.DateField()
    booking_id = serializers.UUIDField()
    gig_title = serializers.CharField()
    gross_paise = serializers.IntegerField()
    commission_paise = serializers.IntegerField()
    commission_gst_paise = serializers.IntegerField()
    tds_paise = serializers.IntegerField()
    net_paise = serializers.IntegerField()
    payout_status = serializers.CharField()
    paid_on = serializers.DateField(allow_null=True)
    utr = serializers.CharField()


class StatementPartySerializer(serializers.Serializer):
    name = serializers.CharField()
    id = serializers.CharField()


class StatementSerializer(serializers.Serializer):
    financial_year = serializers.CharField()
    talent = StatementPartySerializer()
    rows = StatementRowSerializer(many=True)
    totals = serializers.DictField(child=serializers.IntegerField())


class TdsQuarterSerializer(serializers.Serializer):
    quarter = serializers.CharField()
    amount_credited_paise = serializers.IntegerField()
    tds_paise = serializers.IntegerField()


class TdsRowSerializer(serializers.Serializer):
    date = serializers.DateField()
    quarter = serializers.CharField()
    booking_id = serializers.UUIDField()
    gig_title = serializers.CharField()
    amount_credited_paise = serializers.IntegerField()
    tds_paise = serializers.IntegerField()


class DeductorSerializer(serializers.Serializer):
    name = serializers.CharField()
    address = serializers.CharField()
    tan = serializers.CharField()


class DeducteeSerializer(StatementPartySerializer):
    pan_on_file = serializers.BooleanField()


class TdsRecordSerializer(serializers.Serializer):
    financial_year = serializers.CharField()
    section = serializers.CharField()
    deductor = DeductorSerializer()
    deductee = DeducteeSerializer()
    quarters = TdsQuarterSerializer(many=True)
    rows = TdsRowSerializer(many=True)
    total_credited_paise = serializers.IntegerField()
    total_tds_paise = serializers.IntegerField()
    note = serializers.CharField()


class PayoutSerializer(serializers.ModelSerializer):
    escrow_id = serializers.UUIDField(read_only=True)
    booking_id = serializers.UUIDField(source="escrow.booking_id", read_only=True)
    talent_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "escrow_id",
            "booking_id",
            "talent_id",
            "attempt",
            "amount_paise",
            "account_display",
            "status",
            "provider_payout_id",
            "utr",
            "failure_reason",
            "next_attempt_at",
            "processed_at",
            "created_at",
        ]
        read_only_fields = fields


class PayoutRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayoutRun
        fields = [
            "id",
            "trigger",
            "started_by",
            "talent",
            "started_at",
            "finished_at",
            "considered",
            "sent",
            "held",
            "failed",
            "sent_paise",
            "held_reasons",
        ]
        read_only_fields = fields


class PayoutRunDetailSerializer(PayoutRunSerializer):
    payouts = PayoutSerializer(many=True, read_only=True)

    class Meta(PayoutRunSerializer.Meta):
        fields = [*PayoutRunSerializer.Meta.fields, "payouts"]
        read_only_fields = fields


class PayoutRetrySerializer(serializers.Serializer):
    note = serializers.CharField(max_length=500)
