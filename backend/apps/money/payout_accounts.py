"""Linking a talent's payout account (a UPI id or a bank account).

The details go to the payout provider as a fund account and are validated there (a
₹1 deposit or the provider's account check) before any payout can use it. Only the
provider's ids and a masked display ("ab•••@okicici", "HDFC0001234 ••••6789") are
stored; the full UPI id or account number never is.

Replacing a verified account holds payouts for PAYOUT_ACCOUNT_CHANGE_HOLD_HOURS (24)
and tells the talent on every channel they have, so a hijacked login can't quietly
redirect money. The first link has no hold (the first payout needs a verified ID
instead: payouts.py).
"""

import contextlib
import re
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action
from apps.money.gateway.base import GatewayError
from apps.money.gateway.payouts import BankDetails, Validation, get_provider
from apps.money.models import PayoutAccount, PayoutMethod, ValidationStatus

VPA = re.compile(r"^[a-zA-Z0-9.\-_]{2,256}@[a-zA-Z][a-zA-Z0-9.\-]{1,63}$")
IFSC = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
ACCOUNT_NUMBER = re.compile(r"^[0-9]{9,18}$")
AUDIT = ["method", "display", "validation_status", "active", "hold_until"]


class PayoutAccountError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def mask_vpa(vpa: str) -> str:
    name, _, handle = vpa.partition("@")
    return f"{name[:2]}•••@{handle}"


def mask_bank(account_number: str, ifsc: str) -> str:
    return f"{ifsc} ••••{account_number[-4:]}"


def clean(
    method: str, *, vpa: str = "", account_number: str = "", ifsc: str = "", holder_name: str = ""
) -> tuple[str, BankDetails | None, str]:
    """Check the details' shape; returns (vpa, bank, masked display)."""
    if method == PayoutMethod.UPI:
        vpa = vpa.strip()
        if not VPA.match(vpa):
            raise PayoutAccountError("That doesn't look like a UPI id (name@bank).")
        return vpa.lower(), None, mask_vpa(vpa.lower())
    if method == PayoutMethod.BANK:
        account_number = re.sub(r"\s", "", account_number)
        ifsc = ifsc.strip().upper()
        holder_name = " ".join(holder_name.split())
        if not ACCOUNT_NUMBER.match(account_number):
            raise PayoutAccountError("An account number is 9 to 18 digits.")
        if not IFSC.match(ifsc):
            raise PayoutAccountError("That isn't an IFSC code (like HDFC0001234).")
        if len(holder_name) < 2:
            raise PayoutAccountError("Give the name on the account.")
        bank = BankDetails(holder_name[:100], account_number, ifsc)
        return "", bank, mask_bank(account_number, ifsc)
    raise PayoutAccountError("Choose UPI or a bank account.")


def link(talent, *, method: str, request=None, now=None, **details) -> PayoutAccount:
    """Add or replace the talent's payout account and start its validation."""
    now = now or timezone.now()
    vpa, bank, display = clean(method, **details)
    provider = get_provider()
    with transaction.atomic():
        account = PayoutAccount.objects.select_for_update().filter(talent=talent).first()
        replacing = bool(account and account.fund_account_id)
        before = {f: str(getattr(account, f) or "") for f in AUDIT} if account else {}
        try:
            contact_id = (account and account.provider_contact_id) or provider.create_contact(
                name=_name(talent), reference=str(talent.pk)
            )
            fund_account_id = provider.create_fund_account(
                contact_id=contact_id, vpa=vpa, bank=bank
            )
            validation = provider.validate(
                fund_account_id=fund_account_id, reference=f"talent-{talent.pk}"
            )
        except GatewayError as exc:
            raise PayoutAccountError(str(exc), 502) from exc
        old_fund_account = account.fund_account_id if replacing else ""
        if account is None:
            account = PayoutAccount(talent=talent, created_at=now)
        account.method, account.display = method, display
        account.provider_contact_id, account.fund_account_id = contact_id, fund_account_id
        account.active, account.verified_at = False, None
        account.validation_id, account.validation_reason = validation.id, ""
        account.validation_status = ValidationStatus.PENDING
        if replacing:
            account.changed_at = now
            account.hold_until = now + timedelta(hours=settings.PAYOUT_ACCOUNT_CHANGE_HOLD_HOURS)
        account.save()
        log_action(
            actor=talent,
            action="money.payout_account_changed" if replacing else "money.payout_account_linked",
            obj=account,
            before=before,
            after={f: str(getattr(account, f) or "") for f in AUDIT},
            request=request,
        )
        if replacing:
            publish(
                DomainEvent(
                    "money.payout_account_changed",
                    {
                        "talent_id": str(talent.pk),
                        "account": display,
                        "hold_until_ist": timezone.localtime(account.hold_until).strftime(
                            "%d %b, %I:%M %p"
                        ),
                        "dedup_key": f"payout_account:{fund_account_id}",
                        "notify": ["talent"],
                    },
                    occurred_at=now,
                )
            )
        if old_fund_account:
            transaction.on_commit(lambda: _deactivate(old_fund_account))
        apply_validation(account, validation, now=now)
    return account


def _name(talent) -> str:
    profile = getattr(talent, "talent_profile", None)
    return (getattr(profile, "display_name", "") or str(talent.phone))[:50]


def _deactivate(fund_account_id: str) -> None:
    # A failure is harmless: nothing pays to it any more; the provider's dashboard can tidy it.
    with contextlib.suppress(GatewayError):
        get_provider().deactivate_fund_account(fund_account_id)


def apply_validation(account: PayoutAccount, validation: Validation, *, now=None) -> PayoutAccount:
    """Record a validation result (from the start, the webhook or the sync job)."""
    now = now or timezone.now()
    if validation.id != account.validation_id or validation.status == "pending":
        return account
    if account.validation_status != ValidationStatus.PENDING:
        return account
    before = {f: str(getattr(account, f) or "") for f in AUDIT}
    if validation.status == "verified":
        account.validation_status, account.active, account.verified_at = (
            ValidationStatus.VERIFIED,
            True,
            now,
        )
    else:
        account.validation_status, account.active = ValidationStatus.FAILED, False
        account.validation_reason = validation.reason[:200]
    account.save()
    log_action(
        actor=None,
        action=f"money.payout_account_{account.validation_status}",
        obj=account,
        before=before,
        after={f: str(getattr(account, f) or "") for f in AUDIT},
    )
    if validation.status != "verified":
        publish(
            DomainEvent(
                "money.payout_account_failed",
                {
                    "talent_id": str(account.talent_id),
                    "account": account.display,
                    "dedup_key": f"payout_account_failed:{validation.id}",
                    "notify": ["talent"],
                },
                occurred_at=now,
            )
        )
    return account


def on_validation_event(data: dict, now) -> str:
    from apps.money.gateway.payouts import validation_from

    if not data.get("id"):
        return "no validation"
    account = PayoutAccount.objects.select_for_update().filter(validation_id=data["id"]).first()
    if account is None:
        return "not a current payout account"
    apply_validation(account, validation_from(data), now=now)
    return f"payout account {account.validation_status}"


def sync_pending(now) -> dict[str, int]:
    """Job: ask the provider about validations still pending after a few minutes."""
    cutoff = now - timedelta(minutes=5)
    settled = 0
    for pk in PayoutAccount.objects.filter(
        validation_status=ValidationStatus.PENDING, updated_at__lt=cutoff
    ).values_list("pk", flat=True)[:200]:
        with transaction.atomic():
            account = PayoutAccount.objects.select_for_update().get(pk=pk)
            try:
                validation = get_provider().get_validation(account.validation_id)
            except GatewayError:
                continue
            apply_validation(account, validation, now=now)
            settled += account.validation_status != ValidationStatus.PENDING
    return {"validations_settled": settled}
