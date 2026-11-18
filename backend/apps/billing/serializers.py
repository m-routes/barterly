from rest_framework import serializers

from apps.billing.models import FEATURES, Invoice, Plan, Subscription, SubscriptionStatus


class PlanSerializer(serializers.ModelSerializer):
    features = serializers.SerializerMethodField()
    gst_percent = serializers.SerializerMethodField()

    class Meta:
        model = Plan
        fields = [
            "code",
            "name",
            "description",
            "price_paise",
            "currency",
            "gst_percent",
            "max_live_gigs",
            "features",
        ]
        read_only_fields = fields

    def get_features(self, plan) -> dict[str, bool]:
        return {flag: plan.has(flag) for flag in FEATURES}

    def get_gst_percent(self, plan) -> float:
        from django.conf import settings

        return float(settings.BILLING_GST_RATE)


class EntitlementsSerializer(serializers.Serializer):
    plan = serializers.CharField()
    plan_name = serializers.CharField()
    max_live_gigs = serializers.IntegerField(allow_null=True)
    live_gigs = serializers.IntegerField()
    can_post_gig = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)
    features = serializers.DictField(child=serializers.BooleanField())


class SubscriptionSerializer(serializers.ModelSerializer):
    plan = PlanSerializer(read_only=True)
    pending_plan = PlanSerializer(read_only=True, allow_null=True)
    status = serializers.ChoiceField(choices=SubscriptionStatus.choices, read_only=True)

    class Meta:
        model = Subscription
        fields = [
            "id",
            "plan",
            "pending_plan",
            "status",
            "checkout_url",
            "trial_ends_at",
            "current_period_start",
            "current_period_end",
            "payment_failed_at",
            "grace_until",
            "cancel_at_period_end",
            "created_at",
        ]
        read_only_fields = fields


class BillingOverviewSerializer(serializers.Serializer):
    subscription = SubscriptionSerializer(allow_null=True)
    entitlements = EntitlementsSerializer()


class SubscribeSerializer(serializers.Serializer):
    plan = serializers.SlugField()
    coupon = serializers.CharField(max_length=30, required=False, allow_blank=True)


class ChangePlanSerializer(serializers.Serializer):
    plan = serializers.SlugField()


class CancelSubscriptionSerializer(serializers.Serializer):
    at_period_end = serializers.BooleanField(default=True)


class InvoiceSerializer(serializers.ModelSerializer):
    tax_paise = serializers.IntegerField(read_only=True)
    pdf_ready = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "number",
            "plan_name",
            "period_start",
            "period_end",
            "taxable_paise",
            "cgst_paise",
            "sgst_paise",
            "igst_paise",
            "tax_paise",
            "total_paise",
            "gst_rate_percent",
            "place_of_supply",
            "buyer_gstin",
            "issued_at",
            "emailed_at",
            "pdf_ready",
        ]
        read_only_fields = fields

    def get_pdf_ready(self, invoice) -> bool:
        return bool(invoice.pdf_key)


class InvoicePdfLinkSerializer(serializers.Serializer):
    url = serializers.URLField()
    expires_in = serializers.IntegerField()
