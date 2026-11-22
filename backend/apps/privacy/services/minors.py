"""An account that turns out to belong to someone under 18.

flag(): suspend at once, tell the trust team, stop the account showing anywhere, and
audit it. The trust team then decides:
- confirm(): the person is a minor. Their data is purged the way account deletion does
  it (records the business must keep are anonymised), and the account stays closed.
- clear(): an adult after all (a typo, say). The suspension is lifted.

With the trust-and-safety app installed (apps.safety), the suspension is one of its
bans, so its sign-in gate and appeal flow apply. Without it, the account is deactivated.
"""

import logging

from django.apps import apps as django_apps
from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.accounts.services import users
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action
from apps.privacy.models import MinorCase, MinorStatus
from apps.privacy.services import erasure

log = logging.getLogger("apps.privacy.minors")
REASON = "This account looks like it belongs to someone under 18."


class MinorCaseError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


def _suspend(user, *, actor, now) -> str:
    if django_apps.is_installed("apps.safety"):
        from apps.safety.enforcement import suspend

        suspension = suspend(user, kind="ban", reason=REASON, admin=actor, now=now)
        return f"safety.suspension:{suspension.pk}"
    users.set_active(user, False, actor=actor)
    return "accounts.deactivated"


def _lift(case: MinorCase, *, actor, now) -> None:
    if case.restriction.startswith("safety.suspension:"):
        Suspension = django_apps.get_model("safety.Suspension")
        Suspension.objects.filter(pk=case.restriction.split(":", 1)[1]).update(
            lifted_at=now, lifted_by=actor
        )
    else:
        users.set_active(case.user, True, actor=actor)


def _hide(user, now) -> int:
    """Take the person out of view while the trust team looks: withdraw their open
    applications (as the lifecycle allows, so hosts are told) and hide the profile."""
    from apps.applications import services as applications
    from apps.applications.constants import ACTIVE
    from apps.bookings.lifecycle import Actor

    Application = django_apps.get_model("applications.Application")
    count = 0
    for pk in list(
        Application.objects.filter(talent=user, status__in=list(ACTIVE)).values_list(
            "pk", flat=True
        )
    ):
        try:
            applications.transition(
                pk,
                "withdrawn",
                actor=Actor.TALENT,
                user=None,
                reason="Account under review.",
                now=now,
            )
            count += 1
        except applications.InvalidApplicationTransition:
            continue
    count += (
        django_apps.get_model("profiles.TalentProfile")
        .objects.filter(user=user)
        .update(deleted_at=now)
    )
    return count


def flag(user, *, source: str, note: str = "", actor=None, now=None) -> MinorCase:
    now = now or timezone.now()
    with transaction.atomic():
        existing = (
            MinorCase.objects.select_for_update().filter(user=user, status=MinorStatus.OPEN).first()
        )
        if existing:
            return existing
        restriction = _suspend(user, actor=actor, now=now)
        hidden = _hide(user, now)
        case = MinorCase.objects.create(
            user=user,
            source=source,
            status=MinorStatus.OPEN,
            note=note[:500],
            restriction=restriction,
            detected_at=now,
        )
        log_action(
            actor=actor,
            action="privacy.minor_flagged",
            obj=case,
            before={"status": None},
            after={
                "status": case.status,
                "source": source,
                "restriction": restriction,
                "hidden": hidden,
            },
        )
        publish(
            DomainEvent(
                "privacy.minor_flagged",
                {"case_id": str(case.pk), "user_id": str(user.pk), "source": source},
                occurred_at=now,
            )
        )
        transaction.on_commit(lambda: _tell_trust_team(case))
    return case


def _tell_trust_team(case: MinorCase) -> None:
    # No personal data in the email: the case id is enough to open it in the admin.
    log.warning("Suspected minor account", extra={"case_id": str(case.pk), "source": case.source})
    if settings.TRUST_TEAM_EMAILS:
        send_mail(
            "[Barterly trust] Suspected minor account",
            f"Case {case.pk} ({case.get_source_display()}). The account is suspended. "
            f"Open it in the admin under Privacy > Minor cases to confirm or clear it.",
            None,
            list(settings.TRUST_TEAM_EMAILS),
            fail_silently=True,
        )


def confirm(case_id, *, actor, note: str = "", now=None) -> MinorCase:
    now = now or timezone.now()
    with transaction.atomic():
        case = MinorCase.objects.select_for_update().select_related("user").get(pk=case_id)
        if case.status != MinorStatus.OPEN:
            raise MinorCaseError("This case is decided already.")
        summary = erasure.anonymise(case.user, now=now, reason="minor")
        case.status = MinorStatus.CONFIRMED
        case.decided_at, case.decided_by = now, actor
        case.note = (note or case.note)[:500]
        case.save(update_fields=["status", "decided_at", "decided_by", "note"])
        log_action(
            actor=actor,
            action="privacy.minor_confirmed",
            obj=case,
            before={"status": MinorStatus.OPEN},
            after={"status": case.status, "summary": summary},
        )
    return case


def clear(case_id, *, actor, note: str, now=None) -> MinorCase:
    now = now or timezone.now()
    if not note.strip():
        raise MinorCaseError("Say why this person is an adult.", 400)
    with transaction.atomic():
        case = MinorCase.objects.select_for_update().select_related("user").get(pk=case_id)
        if case.status != MinorStatus.OPEN:
            raise MinorCaseError("This case is decided already.")
        _lift(case, actor=actor, now=now)
        django_apps.get_model("profiles.TalentProfile").all_objects.filter(user=case.user).update(
            deleted_at=None
        )
        case.status = MinorStatus.CLEARED
        case.decided_at, case.decided_by, case.note = now, actor, note.strip()[:500]
        case.save(update_fields=["status", "decided_at", "decided_by", "note"])
        log_action(
            actor=actor,
            action="privacy.minor_cleared",
            obj=case,
            before={"status": MinorStatus.OPEN},
            after={"status": case.status, "note": case.note},
        )
    return case
