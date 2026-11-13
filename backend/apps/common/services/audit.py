"""Audit logging for money and status changes.

Call log_action() in the same transaction as the change it records, so a rolled-back
change leaves no entry behind:

    with transaction.atomic():
        before = snapshot(booking, ["status"])
        booking.status = "confirmed"
        booking.save(update_fields=["status"])
        log_action(actor=request.user, action="booking.confirmed", obj=booking,
                   before=before, after=snapshot(booking, ["status"]), request=request)
"""

import ipaddress
import json
from collections.abc import Iterable, Mapping
from typing import Any

from django.core.serializers.json import DjangoJSONEncoder
from django.db import models

from apps.common.models import AuditLog
from apps.common.request_context import get_request_id


def snapshot(instance: models.Model, fields: Iterable[str]) -> dict[str, Any]:
    """JSON-safe dict of the named fields (FKs as their raw id)."""
    data = {}
    for name in fields:
        field = instance._meta.get_field(name)
        data[name] = getattr(instance, field.attname)
    return _json_safe(data)


def client_ip(request) -> str | None:
    """Client IP. Cloud Run's front end puts the client first in X-Forwarded-For."""
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    try:
        return str(ipaddress.ip_address(candidate)) if candidate else None
    except ValueError:
        return None


def log_action(
    *,
    actor,
    action: str,
    obj: models.Model | None = None,
    object_type: str | None = None,
    object_id: Any = None,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    request=None,
) -> AuditLog:
    """Record one audited action. Pass `obj`, or `object_type` and `object_id`."""
    if obj is not None:
        object_type = object_type or obj._meta.label_lower
        object_id = obj.pk if object_id is None else object_id
    if not action or not object_type or object_id in (None, ""):
        raise ValueError("log_action needs an action and a target (obj or object_type + id)")
    if actor is not None and not getattr(actor, "is_authenticated", False):
        actor = None  # AnonymousUser: record as a system/anonymous action
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        before=_json_safe(before) if before is not None else None,
        after=_json_safe(after) if after is not None else None,
        ip=client_ip(request),
        request_id=getattr(request, "request_id", "") or get_request_id(),
    )


def _json_safe(value):
    # Round-trip through DjangoJSONEncoder so Decimals, UUIDs and datetimes become strings
    # now, and the stored value equals what a later read returns.
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))
