from rest_framework import serializers

from apps.money.escrow import DECISIONS
from apps.money.models import DeliverableSubmission, Escrow, EscrowControl, ReconciliationRun


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
