from django.contrib import admin
from django.urls import path


class BarterlyAdminSite(admin.AdminSite):
    """The Django admin plus Barterly's review queues and audit log viewer.

    Each queue checks its own permission (see roles.py); the index only links the
    ones the signed-in admin can use.
    """

    site_header = "Barterly admin"
    site_title = "Barterly admin"
    index_title = "Back office"
    index_template = "backoffice/index.html"

    def get_urls(self):
        from apps.analytics import backoffice as analytics
        from apps.backoffice import views
        from apps.beta import backoffice as beta
        from apps.support import backoffice as support

        queues = [
            path(
                "queues/verification/",
                self.admin_view(views.verification_queue),
                name="verification_queue",
            ),
            path(
                "queues/verification/<uuid:case_id>/",
                self.admin_view(views.verification_case),
                name="verification_case",
            ),
            path("queues/gigs/", self.admin_view(views.gig_queue), name="gig_queue"),
            path(
                "queues/gigs/<uuid:gig_id>/",
                self.admin_view(views.gig_review),
                name="gig_review",
            ),
            path("support/", self.admin_view(support.inbox), name="support_inbox"),
            path(
                "support/requests/<uuid:ticket_id>/",
                self.admin_view(support.ticket_page),
                name="support_ticket",
            ),
            path(
                "support/people/", self.admin_view(support.find_person), name="support_find_person"
            ),
            path(
                "support/people/<uuid:user_id>/",
                self.admin_view(support.person_timeline),
                name="support_timeline",
            ),
            path("kpis/", self.admin_view(analytics.dashboard), name="analytics_kpis"),
            path("beta/invites/new/", self.admin_view(beta.invite_batch), name="beta_invite_batch"),
            path(
                "beta/invites/<str:cohort>.csv",
                self.admin_view(beta.invite_csv),
                name="beta_invite_csv",
            ),
            path(
                "beta/onboarding/", self.admin_view(beta.onboarding_tracker), name="beta_onboarding"
            ),
            path("beta/review/", self.admin_view(beta.safety_review), name="beta_safety_review"),
        ]
        return queues + super().get_urls()

    def each_context(self, request):
        context = super().each_context(request)
        user = request.user
        context["queues"] = [
            q
            for q in (
                (
                    "Verification queue",
                    "admin:verification_queue",
                    "backoffice.review_verification",
                ),
                ("Gig approval queue", "admin:gig_queue", "backoffice.review_gigs"),
                ("Audit log", "admin:common_auditlog_changelist", "backoffice.view_audit_log"),
                ("Support inbox", "admin:support_inbox", "support.handle_tickets"),
                ("Find a person (timeline)", "admin:support_find_person", "support.view_timeline"),
                ("Beta KPIs", "admin:analytics_kpis", "analytics.view_kpis"),
                (
                    "Weekly dispute and safety review",
                    "admin:beta_safety_review",
                    "beta.review_safety",
                ),
                ("Beta onboarding tracker", "admin:beta_onboarding", "beta.view_onboarding"),
                ("Make invite codes", "admin:beta_invite_batch", "beta.manage_invites"),
            )
            if user.is_active and user.has_perm(q[2])
        ]
        return context
