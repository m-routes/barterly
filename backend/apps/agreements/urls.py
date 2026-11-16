from django.urls import path

from apps.agreements import views

app_name = "agreements"

urlpatterns = [
    path("agreements/", views.AgreementListView.as_view(), name="list"),
    path("agreements/<uuid:agreement_id>/", views.AgreementDetailView.as_view(), name="detail"),
    path(
        "bookings/<uuid:booking_id>/agreement/",
        views.BookingAgreementView.as_view(),
        name="for-booking",
    ),
    path(
        "bookings/<uuid:booking_id>/agreement/changes/",
        views.ProposeChangeView.as_view(),
        name="propose-change",
    ),
    path("agreement-versions/<uuid:version_id>/pdf/", views.PdfView.as_view(), name="pdf"),
    path("agreement-versions/<uuid:version_id>/sign/", views.SignView.as_view(), name="sign"),
    path(
        "agreement-versions/<uuid:version_id>/decline/",
        views.DeclineChangeView.as_view(),
        name="decline",
    ),
]
