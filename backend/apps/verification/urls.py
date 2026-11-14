from django.urls import path

from apps.verification import views

app_name = "verification"

urlpatterns = [
    path("verification/me/", views.MyVerificationView.as_view(), name="me"),
    path("verification/checks/id/", views.StartIdCheckView.as_view(), name="id-start"),
    path("verification/checks/business/", views.BusinessCheckView.as_view(), name="business"),
    path("verification/checks/property/", views.PropertyCheckView.as_view(), name="property"),
    path("verification/checks/social/", views.SocialCheckView.as_view(), name="social"),
    path(
        "verification/checks/certificates/",
        views.CertificatesCheckView.as_view(),
        name="certificates",
    ),
    path("verification/checks/reference/", views.ReferenceCheckView.as_view(), name="reference"),
    path("verification/webhooks/kyc/", views.KycWebhookView.as_view(), name="kyc-webhook"),
    path("verification/admin/cases/", views.AdminCaseListView.as_view(), name="admin-cases"),
    path(
        "verification/admin/cases/<uuid:case_id>/",
        views.AdminCaseDetailView.as_view(),
        name="admin-case",
    ),
    path(
        "verification/admin/cases/<uuid:case_id>/decision/",
        views.AdminDecisionView.as_view(),
        name="admin-decision",
    ),
]
