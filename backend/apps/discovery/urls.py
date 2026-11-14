from django.urls import path

from apps.discovery import views

app_name = "discovery"

urlpatterns = [
    path("gigs/saved-searches/", views.SavedSearchListView.as_view(), name="saved-searches"),
    path(
        "gigs/saved-searches/<uuid:search_id>/",
        views.SavedSearchDetailView.as_view(),
        name="saved-search",
    ),
]
