from django.urls import path

from apps.deliverables import views

app_name = "deliverables"

urlpatterns = [
    path(
        "bookings/<uuid:booking_id>/deliverables/items/",
        views.BookingDeliverablesView.as_view(),
        name="for-booking",
    ),
    path("deliverables/items/<uuid:deliverable_id>/", views.DueDateView.as_view(), name="item"),
    path(
        "deliverables/items/<uuid:deliverable_id>/submit/",
        views.SubmitView.as_view(),
        name="submit",
    ),
    path(
        "deliverables/items/<uuid:deliverable_id>/review/",
        views.ReviewView.as_view(),
        name="review",
    ),
    path(
        "deliverables/items/<uuid:deliverable_id>/stats/",
        views.ManualStatsView.as_view(),
        name="stats",
    ),
    path("content/to-review/", views.ToReviewView.as_view(), name="to-review"),
    path("content/library/", views.LibraryView.as_view(), name="library"),
]
