"""Review queues in the admin. Decisions go through the same services as the API, so
they are checked, keep badges in step, and write AuditLog rows."""

from datetime import timedelta

from django.contrib import admin, messages
from django.contrib.auth.decorators import permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from apps.backoffice.forms import GigDecisionForm, VerificationDecisionForm
from apps.backoffice.rules import gig_rules
from apps.common.models import AuditLog
from apps.gigs.constants import Actor, GigStatus
from apps.gigs.models import Gig
from apps.gigs.services import InvalidGigTransition, transition
from apps.verification.constants import CaseStatus, CheckType
from apps.verification.models import VerificationCase
from apps.verification.services.cases import InvalidTransition, decide

PAGE_SIZE = 50
# Cases waiting longer than this are flagged as overdue in the queue.
REVIEW_TARGET = timedelta(hours=48)
OPEN = [CaseStatus.SUBMITTED, CaseStatus.IN_REVIEW]


def _context(request, **extra):
    return {**admin.site.each_context(request), **extra}


def _history(obj) -> list[dict]:
    entries = (
        AuditLog.objects.filter(object_type=obj._meta.label_lower, object_id=str(obj.pk))
        .select_related("actor")
        .order_by("-created_at")[:20]
    )
    return [
        {
            "entry": entry,
            # Cases keep their reason in "reason", gigs in "status_reason".
            "note": (entry.after or {}).get("reason")
            or (entry.after or {}).get("status_reason")
            or "",
        }
        for entry in entries
    ]


@permission_required("backoffice.review_verification", raise_exception=True)
def verification_queue(request):
    status = request.GET.get("status", "open")
    check = request.GET.get("check", "")
    qs = VerificationCase.objects.select_related("user", "property", "reviewer")
    if status == "open":
        qs = qs.filter(status__in=OPEN)
    elif status in CaseStatus.values:
        qs = qs.filter(status=status)
    if check in CheckType.values:
        qs = qs.filter(check_type=check)
    # Oldest first: the longest wait is reviewed next.
    qs = qs.order_by("submitted_at", "created_at")
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    now = timezone.now()
    rows = [
        {
            "case": case,
            "waiting": now - case.submitted_at if case.submitted_at else None,
            "overdue": bool(
                case.status in OPEN
                and case.submitted_at
                and now - case.submitted_at > REVIEW_TARGET
            ),
        }
        for case in page
    ]
    return TemplateResponse(
        request,
        "backoffice/verification_queue.html",
        _context(
            request,
            title="Verification queue",
            rows=rows,
            page=page,
            status=status,
            check=check,
            statuses=[("open", "Waiting for a decision"), *CaseStatus.choices],
            checks=CheckType.choices,
            target_hours=int(REVIEW_TARGET.total_seconds() // 3600),
        ),
    )


@permission_required("backoffice.review_verification", raise_exception=True)
def verification_case(request, case_id):
    case = get_object_or_404(
        VerificationCase.objects.select_related("user", "property", "reviewer"), pk=case_id
    )
    form = VerificationDecisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            decide(
                case.pk,
                form.cleaned_data["decision"],
                reviewer=request.user,
                reason=form.cleaned_data["reason"],
                request=request,
            )
        except (InvalidTransition, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "Decision saved.")
            return redirect(reverse("admin:verification_case", args=[case.pk]))
    other_checks = (
        VerificationCase.objects.filter(user=case.user).exclude(pk=case.pk).order_by("check_type")
    )
    return TemplateResponse(
        request,
        "backoffice/verification_case.html",
        _context(
            request,
            title=f"{case.get_check_type_display()} for {case.user.phone}",
            case=case,
            form=form,
            details=sorted((case.details or {}).items()),
            documents=case.documents.all(),
            badges=case.user.badges.filter(revoked_at__isnull=True),
            other_checks=other_checks,
            history=_history(case),
            can_decide=case.status in OPEN,
            can_revoke=case.status == CaseStatus.APPROVED,
        ),
    )


@permission_required("backoffice.review_gigs", raise_exception=True)
def gig_queue(request):
    qs = (
        Gig.objects.filter(status=GigStatus.IN_REVIEW)
        .select_related("vendor", "property")
        .prefetch_related("vendor__badges")
        .order_by("submitted_at", "created_at")
    )
    page = Paginator(qs, PAGE_SIZE).get_page(request.GET.get("page"))
    now = timezone.now()
    rows = [
        {
            "gig": gig,
            "report": gig_rules(gig),
            "waiting": now - gig.submitted_at if gig.submitted_at else None,
        }
        for gig in page
    ]
    flagged = request.GET.get("flagged") == "1"
    if flagged:
        rows = [r for r in rows if r["report"].breaks]
    return TemplateResponse(
        request,
        "backoffice/gig_queue.html",
        _context(
            request,
            title="Gig approval queue",
            rows=rows,
            page=page,
            flagged=flagged,
            query="flagged=1" if flagged else "",
        ),
    )


@permission_required("backoffice.review_gigs", raise_exception=True)
def gig_review(request, gig_id):
    gig = get_object_or_404(Gig.objects.select_related("vendor", "property"), pk=gig_id)
    form = GigDecisionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        target = GigStatus.LIVE if form.cleaned_data["decision"] == "approve" else GigStatus.DRAFT
        try:
            transition(
                gig.pk,
                target,
                actor=Actor.ADMIN,
                user=request.user,
                reason=form.cleaned_data["reason"],
                request=request,
            )
        except ValidationError as exc:
            for messages_ in exc.message_dict.values():
                for message in messages_:
                    form.add_error(None, message)
        except (InvalidGigTransition, ValueError) as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request, "Gig approved." if target == GigStatus.LIVE else "Sent back to the vendor."
            )
            return redirect(reverse("admin:gig_queue"))
    return TemplateResponse(
        request,
        "backoffice/gig_review.html",
        _context(
            request,
            title=gig.title,
            gig=gig,
            form=form,
            report=gig_rules(gig),
            history=_history(gig),
            can_decide=gig.status == GigStatus.IN_REVIEW,
        ),
    )
