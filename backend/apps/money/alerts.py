"""Alerts for the money team: an error log line (Sentry picks it up), an audit entry,
and an email to settings.ESCROW_ALERT_EMAILS."""

import logging

from django.conf import settings
from django.core.mail import send_mail

from apps.common.services.audit import log_action

log = logging.getLogger("apps.money.alerts")


def raise_alert(subject: str, details: dict, *, obj=None) -> None:
    log.error("MONEY ALERT: %s %s", subject, details)
    if obj is not None:
        log_action(actor=None, action="money.alert", obj=obj, after={"subject": subject, **details})
    else:
        log_action(
            actor=None,
            action="money.alert",
            object_type="money",
            object_id="-",
            after={"subject": subject, **details},
        )
    if settings.ESCROW_ALERT_EMAILS:
        lines = "\n".join(f"{k}: {v}" for k, v in details.items())
        send_mail(
            f"[Barterly money] {subject}",
            lines or subject,
            None,
            list(settings.ESCROW_ALERT_EMAILS),
            fail_silently=True,
        )
