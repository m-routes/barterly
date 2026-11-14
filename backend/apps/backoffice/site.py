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
        from apps.backoffice import views

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
            )
            if user.is_active and user.has_perm(q[2])
        ]
        return context
