from django.urls import path

from apps.privacy import views

app_name = "privacy"

urlpatterns = [
    path("privacy/documents/", views.DocumentsView.as_view(), name="documents"),
    path("privacy/grievance-officer/", views.GrievanceOfficerView.as_view(), name="grievance"),
    path("privacy/consents/", views.ConsentsView.as_view(), name="consents"),
    path("privacy/consents/history/", views.ConsentHistoryView.as_view(), name="consent-history"),
    path("privacy/exports/", views.ExportsView.as_view(), name="exports"),
    path(
        "privacy/exports/<uuid:export_id>/link/", views.ExportLinkView.as_view(), name="export-link"
    ),
    path("privacy/deletion/", views.DeletionView.as_view(), name="deletion"),
    path("privacy/corrections/", views.CorrectionsView.as_view(), name="corrections"),
]
