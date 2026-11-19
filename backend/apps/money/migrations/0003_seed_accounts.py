"""Seed the chart of accounts. Reversing removes only accounts nothing has posted to."""

from django.db import migrations

# A copy, not an import: a migration must not change when the code does.
ACCOUNTS = {
    "gateway:clearing": ("Gateway clearing", "asset"),
    "escrow:held": ("Escrow held for bookings", "liability"),
    "talent:payable": ("Payable to talent", "liability"),
    "revenue:commission": ("Commission", "revenue"),
    "revenue:fee_recovery": ("Gateway fee recovered from hosts", "revenue"),
    "tax:gst_output": ("GST output", "liability"),
    "tax:gst_input": ("GST input credit", "asset"),
    "tax:tds_payable": ("TDS payable", "liability"),
    "expense:gateway_fees": ("Gateway fees", "expense"),
    "equity:adjustments": ("Adjustments", "equity"),
}


def seed(apps, schema_editor):
    Account = apps.get_model("money", "Account")
    for code, (name, kind) in ACCOUNTS.items():
        Account.objects.update_or_create(code=code, defaults={"name": name, "kind": kind})


def unseed(apps, schema_editor):
    Account = apps.get_model("money", "Account")
    LedgerEntry = apps.get_model("money", "LedgerEntry")
    used = set(LedgerEntry.objects.values_list("debit_account__code", flat=True)) | set(
        LedgerEntry.objects.values_list("credit_account__code", flat=True)
    )
    Account.objects.filter(code__in=set(ACCOUNTS) - used).delete()


class Migration(migrations.Migration):
    dependencies = [("money", "0002_ledger_append_only")]

    operations = [migrations.RunPython(seed, unseed)]
