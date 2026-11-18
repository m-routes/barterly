import importlib
from datetime import datetime

from django.conf import settings

from apps.billing.gateway.fake import signed
from apps.billing.models import Plan
from apps.profiles.tests.factories import VendorProfileFactory


def plans_on_sale() -> dict[str, Plan]:
    """The seeded plans (tests run without migrations, so seed them here), with
    Razorpay plan ids (the migration leaves them blank)."""
    seed = importlib.import_module("apps.billing.migrations.0002_seed_plans")
    found = {}
    for data in seed.PLANS:
        plan, _ = Plan.objects.update_or_create(
            code=data["code"], defaults={**data, "gateway_plan_id": f"plan_{data['code']}"}
        )
        found[plan.code] = plan
    return found


def vendor(**profile):
    return VendorProfileFactory(**profile).user


def ts(moment: datetime) -> int:
    return int(moment.timestamp())


def webhook(event: str, sub_id: str, event_id: str, *, payment: dict | None = None, **entity):
    """A signed Razorpay webhook (body, headers)."""
    payload = {"subscription": {"entity": {"id": sub_id, **entity}}}
    if payment:
        payload["payment"] = {"entity": payment}
    return signed(
        {"entity": "event", "event": event, "payload": payload, "created_at": 1},
        settings.RAZORPAY_WEBHOOK_SECRET,
        event_id,
    )
