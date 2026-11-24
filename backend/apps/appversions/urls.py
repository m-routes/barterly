from django.urls import path

from apps.appversions import views

urlpatterns = [
    path("app/version/", views.AppVersionView.as_view(), name="app-version"),
    path("admin/app-versions/", views.AdminAppVersionListView.as_view(), name="app-versions-admin"),
    path(
        "admin/app-versions/<slug:platform>/",
        views.AdminAppVersionView.as_view(),
        name="app-versions-admin-set",
    ),
]
