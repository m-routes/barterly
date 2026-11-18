from django.contrib import admin

from apps.billing.models import Coupon, Invoice, Plan, Subscription, WebhookEvent


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "code",
        "price_paise",
        "max_live_gigs",
        "gateway_plan_id",
        "is_public",
        "position",
    ]
    list_editable = ["is_public", "position"]


@admin.register(Coupon)
class CouponAdmin(admin.ModelAdmin):
    list_display = ["code", "trial_days", "redemptions", "max_redemptions", "valid_until", "active"]
    readonly_fields = ["redemptions", "created_at"]


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    """Read-only: subscriptions change through the gateway's webhooks (audited)."""

    list_display = ["vendor", "plan", "status", "current_period_end", "grace_until", "created_at"]
    list_filter = ["status", "plan"]
    search_fields = ["vendor__phone", "gateway_subscription_id"]
    readonly_fields = [f.name for f in Subscription._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ["number", "vendor", "total_paise", "issued_at", "emailed_at"]
    search_fields = ["number", "vendor__phone", "gateway_payment_id", "buyer_gstin"]
    readonly_fields = [f.name for f in Invoice._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ["received_at", "event", "event_id", "outcome", "processed_at"]
    list_filter = ["event"]
    search_fields = ["event_id"]
    readonly_fields = [f.name for f in WebhookEvent._meta.fields]

    def has_add_permission(self, request):
        return False
