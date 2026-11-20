"""Money in the admin: everything read-only except the kill switch. Ledger rows can't be
changed at all (database triggers); escrows change only through the API, audited."""

from django.contrib import admin
from django.utils import timezone

from apps.common.services.audit import log_action
from apps.money.models import (
    Account,
    DeliverableSubmission,
    Escrow,
    EscrowControl,
    GatewayEvent,
    LedgerEntry,
    LedgerTransaction,
    Payout,
    PayoutAccount,
    PayoutRun,
    ReconciliationRun,
)


class ReadOnly(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Account)
class AccountAdmin(ReadOnly):
    list_display = ["code", "name", "kind", "currency"]


class EntryInline(admin.TabularInline):
    model = LedgerEntry
    fields = ["line", "debit_account", "credit_account", "amount_paise", "reference"]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(LedgerTransaction)
class LedgerTransactionAdmin(ReadOnly):
    list_display = ["created_at", "kind", "idempotency_key", "booking", "reference"]
    list_filter = ["kind"]
    search_fields = ["idempotency_key", "reference", "booking__id"]
    inlines = [EntryInline]

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Escrow)
class EscrowAdmin(ReadOnly):
    list_display = [
        "booking",
        "status",
        "payout_status",
        "frozen",
        "stipend_paise",
        "released_paise",
        "refund_paise",
        "created_at",
    ]
    list_filter = ["status", "payout_status", "frozen"]
    search_fields = ["booking__id", "gateway_order_id", "gateway_payment_id", "payout_transfer_id"]


@admin.register(PayoutAccount)
class PayoutAccountAdmin(ReadOnly):
    list_display = [
        "talent",
        "method",
        "display",
        "validation_status",
        "active",
        "hold_until",
        "pan_on_file",
    ]
    list_filter = ["method", "validation_status", "active"]
    search_fields = ["talent__phone", "fund_account_id", "display"]


@admin.register(DeliverableSubmission)
class DeliverableSubmissionAdmin(ReadOnly):
    list_display = ["booking", "submitted_at", "review", "reviewed_at"]
    list_filter = ["review"]


@admin.register(GatewayEvent)
class GatewayEventAdmin(ReadOnly):
    list_display = ["received_at", "event", "event_id", "outcome"]
    list_filter = ["event"]
    search_fields = ["event_id"]


@admin.register(ReconciliationRun)
class ReconciliationRunAdmin(ReadOnly):
    list_display = ["day", "ok", "created_at"]
    list_filter = ["ok"]


@admin.register(EscrowControl)
class EscrowControlAdmin(admin.ModelAdmin):
    """The kill switch. Changing it needs money.toggle_kill_switch, and is audited."""

    list_display = ["__str__", "reason", "changed_by", "changed_at"]
    fields = ["paused", "reason", "changed_by", "changed_at"]
    readonly_fields = ["changed_by", "changed_at"]

    def has_add_permission(self, request):
        return (
            request.user.has_perm("money.toggle_kill_switch") and not EscrowControl.objects.exists()
        )

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("money.toggle_kill_switch")

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.changed_by, obj.changed_at = request.user, timezone.now()
        super().save_model(request, obj, form, change)
        log_action(
            actor=request.user,
            action="money.kill_switch",
            obj=obj,
            after={"paused": obj.paused, "reason": obj.reason},
            request=request,
        )


class PayoutInline(admin.TabularInline):
    model = Payout
    fields = [
        "escrow",
        "talent",
        "attempt",
        "amount_paise",
        "account_display",
        "status",
        "failure_reason",
        "next_attempt_at",
    ]
    readonly_fields = fields
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PayoutRun)
class PayoutRunAdmin(ReadOnly):
    list_display = ["started_at", "trigger", "considered", "sent", "held", "failed", "sent_paise"]
    list_filter = ["trigger"]
    inlines = [PayoutInline]


@admin.register(Payout)
class PayoutAdmin(ReadOnly):
    list_display = [
        "created_at",
        "talent",
        "amount_paise",
        "status",
        "attempt",
        "next_attempt_at",
        "failure_reason",
    ]
    list_filter = ["status"]
    search_fields = ["provider_payout_id", "utr", "talent__phone", "escrow__booking__id"]
