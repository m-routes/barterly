"""Back-office pages for the beta: invite codes, the onboarding tracker and the weekly
dispute and safety review. Linked from the admin index (apps.backoffice.site)."""

import csv
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.http import HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from apps.backoffice.views import _context
from apps.beta import invites, onboarding, review
from apps.beta.forms import InviteBatchForm, SafetyReviewForm
from apps.beta.models import InviteCode
from apps.common.services.audit import log_action


@permission_required("beta.manage_invites", raise_exception=True)
def invite_batch(request):
    form = InviteBatchForm(request.POST or None)
    made = []
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            made = invites.generate(
                count=data.get("count") or 0,
                labels=data["label_list"],
                cohort=data["cohort"],
                role=data.get("role") or "",
                max_uses=data["max_uses"],
                expires_at=timezone.now() + timedelta(days=data["expires_in_days"]),
                by=request.user,
                request=request,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, f"Made {len(made)} code(s) in {data['cohort']}.")
    return TemplateResponse(
        request,
        "beta/invite_batch.html",
        _context(request, title="Make invite codes", form=form, made=made),
    )


@permission_required("beta.manage_invites", raise_exception=True)
def invite_csv(request, cohort):
    rows = InviteCode.objects.filter(cohort=cohort).order_by("label", "created_at")
    log_action(
        actor=request.user,
        action="beta.invites_exported",
        object_type="beta.cohort",
        object_id=cohort,
        after={"count": rows.count()},
        request=request,
    )
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="invites-{cohort}.csv"'
    writer = csv.writer(response)
    writer.writerow(["code", "label", "role", "state", "used", "max_uses", "expires_at"])
    for invite in rows:
        writer.writerow(
            [
                invite.display,
                invite.label,
                invite.role or "any",
                invite.state(),
                invite.used,
                invite.max_uses,
                invite.expires_at.isoformat() if invite.expires_at else "",
            ]
        )
    return response


@permission_required("beta.view_onboarding", raise_exception=True)
def onboarding_tracker(request):
    cohorts = onboarding.cohorts()
    cohort = request.GET.get("cohort") or (cohorts[-1] if cohorts else "")
    rows = onboarding.rows_for(cohort) if cohort else []
    stuck = request.GET.get("stuck") == "1"
    shown = [r for r in rows if r.next_step != "All done"] if stuck else rows
    return TemplateResponse(
        request,
        "beta/onboarding.html",
        _context(
            request,
            title="Beta onboarding tracker",
            cohorts=cohorts,
            cohort=cohort,
            rows=shown,
            total=len(rows),
            funnel=onboarding.funnel(rows),
            steps=onboarding.STEPS,
            stuck=stuck,
        ),
    )


def _week(value: str | None) -> date:
    try:
        return review.week_of(date.fromisoformat(value)) if value else review.this_week()
    except ValueError:
        return review.this_week()


@permission_required("beta.review_safety", raise_exception=True)
def safety_review(request):
    week = _week(request.GET.get("week") or request.POST.get("week"))
    if request.method == "POST":
        form = SafetyReviewForm(request.POST)
        if form.is_valid():
            try:
                review.record(
                    form.cleaned_data["kind"],
                    form.cleaned_data["object_id"],
                    outcome=form.cleaned_data["outcome"],
                    notes=form.cleaned_data["notes"],
                    by=request.user,
                    week=week,
                    request=request,
                )
            except ValueError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "Review recorded.")
        else:
            messages.error(request, "Choose an outcome.")
        return redirect(f"{reverse('admin:beta_safety_review')}?week={week.isoformat()}")
    items = review.items_for(week)
    overdue = review.overdue()
    return TemplateResponse(
        request,
        "beta/safety_review.html",
        _context(
            request,
            title=f"Dispute and safety review: week of {week:%d %b %Y}",
            week=week,
            previous=week - timedelta(weeks=1),
            following=week + timedelta(weeks=1),
            items=[
                (item, SafetyReviewForm(initial={"kind": item.kind, "object_id": item.object_id}))
                for item in items
            ],
            reviewed=sum(1 for i in items if i.review),
            overdue=overdue,
        ),
    )
