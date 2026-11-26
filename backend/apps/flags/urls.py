from django.urls import path

from apps.flags import views

urlpatterns = [
    path("flags/", views.FlagValuesView.as_view(), name="flags"),
    path("admin/flags/", views.AdminFlagListView.as_view(), name="flags-admin"),
    path("admin/flags/<slug:key>/", views.AdminFlagView.as_view(), name="flags-admin-set"),
]
