"""Applying to gigs, and moving applications between statuses.

Every status change writes an AuditLog row. A new application queues a notification
for the vendor (delivered in Phase 3).
"""

from dataclasses import dataclass
from datetime import date

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.applications.constants import ACTIVE, TRANSITIONS, Actor, ApplicationStatus
from apps.applications.models import Application, ApplicationAttachment, AttachmentKind
from apps.applications.rules import Reason, blocking_reasons, gig_end
from apps.common.services.audit import log_action, snapshot
from apps.discovery.scoring import GigFacts, TalentFacts, fit_score
from apps.discovery.services import talent_signals
from apps.gigs.models import Gig
from apps.media.models import MediaFile, MediaStatus
from apps.media.policy import Kind
from apps.notifications.services import queue_notification
from apps.profiles.models import TalentProfile

NEW_APPLICATION_KIND = "applications.new"
UNUSABLE_MEDIA = (MediaStatus.REJECTED, MediaStatus.QUARANTINED, MediaStatus.PENDING_UPLOAD)
MEDIA_KIND_FOR = {
    AttachmentKind.PHOTO: Kind.PHOTO,
    AttachmentKind.VIDEO: Kind.VIDEO,
    AttachmentKind.DOCUMENT: Kind.DOCUMENT,
}


class ApplicationBlocked(Exception):
    """The talent can't apply; `reasons` says every reason why."""

    def __init__(self, reasons: list[Reason]):
        super().__init__("; ".join(r.message for r in reasons))
        self.reasons = reasons


class InvalidApplicationTransition(Exception):
    """That status change doesn't exist, or this actor may not make it."""


@dataclass(frozen=True)
class AttachmentInput:
    kind: str
    media_id: str | None = None
    url: str = ""
    title: str = ""


def apply(
    talent,
    gig_id,
    *,
    pitch: str,
    answers: list[str],
    proposed_start: date,
    proposed_end: date,
    attachments: list[AttachmentInput],
    request=None,
) -> Application:
    with transaction.atomic():
        gig = Gig.objects.select_for_update().select_related("vendor").get(pk=gig_id)
        profile = TalentProfile.all_objects.filter(user=talent).prefetch_related("skills").first()
        reasons = blocking_reasons(
            talent,
            gig,
            profile,
            proposed_start=proposed_start,
            proposed_end=proposed_end,
            answers=answers,
            today=timezone.localdate(),
        )
        media = _attachment_media(talent, attachments, reasons)
        if reasons:
            raise ApplicationBlocked(reasons)

        fit = _fit(talent, profile, gig, proposed_start, proposed_end)
        try:
            with transaction.atomic():
                application = Application.objects.create(
                    gig=gig,
                    talent=talent,
                    pitch=pitch.strip(),
                    answers=[
                        {"question": q, "answer": a.strip()}
                        for q, a in zip(gig.screening_questions, answers, strict=True)
                    ],
                    proposed_start=proposed_start,
                    proposed_end=proposed_end,
                    fit_score=fit.score,
                    fit_breakdown=fit.breakdown(),
                )
        except IntegrityError as exc:  # a parallel request applied first
            raise ApplicationBlocked(
                [Reason("already_applied", "You already have an active application for this gig.")]
            ) from exc
        ApplicationAttachment.objects.bulk_create(
            ApplicationAttachment(
                application=application,
                kind=item.kind,
                media=media.get(str(item.media_id)) if item.media_id else None,
                url=item.url,
                title=item.title,
                position=position,
            )
            for position, item in enumerate(attachments)
        )
        log_action(
            actor=talent,
            action="application.applied",
            obj=application,
            after={"status": application.status, "gig": str(gig.pk), "fit_score": fit.score},
            request=request,
        )
        queue_notification(
            gig.vendor,
            NEW_APPLICATION_KIND,
            {
                "application_id": str(application.pk),
                "gig_id": str(gig.pk),
                "gig_title": gig.title,
                "talent_name": profile.display_name,
                "fit_score": fit.score,
            },
        )
    return application


def _attachment_media(talent, attachments, reasons: list[Reason]) -> dict[str, MediaFile]:
    wanted = {str(a.media_id): MEDIA_KIND_FOR[a.kind] for a in attachments if a.media_id}
    found = {
        str(m.pk): m
        for m in MediaFile.objects.filter(pk__in=list(wanted), owner=talent).exclude(
            status__in=UNUSABLE_MEDIA
        )
    }
    bad = [mid for mid, kind in wanted.items() if mid not in found or found[mid].kind != kind]
    if bad:
        reasons.append(
            Reason("attachment_unusable", f"These uploads can't be attached: {', '.join(bad)}.")
        )
    return found


def _fit(talent, profile, gig, start: date, end: date):
    facts = TalentFacts(
        skills=frozenset(s.slug for s in profile.skills.all()),
        available_from=start,
        available_to=end,
        **talent_signals(talent),
    )
    return fit_score(
        facts,
        GigFacts(
            skills=frozenset(gig.skills.values_list("slug", flat=True)),
            start_date=gig.start_date,
            end_date=gig_end(gig),
        ),
        weights=settings.DISCOVERY_FIT_WEIGHTS,
        distance_zero_km=settings.DISCOVERY_DISTANCE_ZERO_KM,
    )


def transition(
    application_id, to: str, *, actor: str, user=None, reason: str = "", request=None
) -> Application:
    """Move an application if TRANSITIONS lets this actor do it. Audited."""
    with transaction.atomic():
        application = Application.objects.select_for_update().get(pk=application_id)
        allowed = TRANSITIONS.get((application.status, to))
        if allowed is None:
            raise InvalidApplicationTransition(
                f"A {application.get_status_display().lower()} application can't become {to}."
            )
        if actor not in allowed:
            raise InvalidApplicationTransition(
                f"Only the {' or '.join(sorted(allowed))} can do that."
            )
        before = snapshot(application, ["status", "status_reason"])
        application.status = to
        application.status_reason = reason.strip()
        if to not in ACTIVE:
            application.decided_at = timezone.now()
        application.save(update_fields=["status", "status_reason", "decided_at", "updated_at"])
        log_action(
            actor=user,
            action=f"application.{to}",
            obj=application,
            before=before,
            after={**snapshot(application, ["status", "status_reason"]), "by": actor},
            request=request,
        )
    return application


def withdraw(application_id, *, talent, reason: str = "", request=None) -> Application:
    """The talent withdraws: allowed any time until an offer is accepted."""
    if not Application.objects.filter(pk=application_id, talent=talent).exists():
        raise Application.DoesNotExist
    return transition(
        application_id,
        ApplicationStatus.WITHDRAWN,
        actor=Actor.TALENT,
        user=talent,
        reason=reason,
        request=request,
    )
