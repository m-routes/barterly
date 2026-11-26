from django.urls import path

from apps.bookings import views

app_name = "bookings"

urlpatterns = [
    path(
        "applications/<uuid:application_id>/accept/",
        views.AcceptOfferView.as_view(),
        name="accept",
    ),
    path("bookings/", views.BookingListView.as_view(), name="list"),
    path("bookings/<uuid:booking_id>/", views.BookingDetailView.as_view(), name="detail"),
    path(
        "bookings/<uuid:booking_id>/transition/",
        views.BookingTransitionView.as_view(),
        name="transition",
    ),
    path("bookings/<uuid:booking_id>/cancel/", views.CancelView.as_view(), name="cancel"),
    path("bookings/<uuid:booking_id>/details/", views.UnlockedView.as_view(), name="details"),
    path("jobs/<slug:job>/", views.JobView.as_view(), name="job"),
    path("tasks/<str:name>/", views.TaskView.as_view(), name="task"),
]
