from django.urls import path

from apps.applications import views

app_name = "applications"

urlpatterns = [
    path(
        "gigs/<uuid:gig_id>/applications/",
        views.GigApplicationsView.as_view(),
        name="gig-applications",
    ),
    path("applications/mine/", views.MyApplicationsView.as_view(), name="mine"),
    path(
        "applications/<uuid:application_id>/",
        views.ApplicationDetailView.as_view(),
        name="detail",
    ),
    path(
        "applications/<uuid:application_id>/withdraw/",
        views.WithdrawView.as_view(),
        name="withdraw",
    ),
]
