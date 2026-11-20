from django.urls import path

from apps.attendance import views

app_name = "attendance"

urlpatterns = [
    path("bookings/<uuid:booking_id>/attendance/", views.AttendanceView.as_view(), name="record"),
    path("bookings/<uuid:booking_id>/attendance/pass/", views.PassView.as_view(), name="pass"),
    path(
        "bookings/<uuid:booking_id>/attendance/check-out/",
        views.CheckOutView.as_view(),
        name="check-out",
    ),
    path(
        "bookings/<uuid:booking_id>/attendance/no-show/",
        views.NoShowView.as_view(),
        name="no-show",
    ),
    path("bookings/<uuid:booking_id>/hours/", views.HoursView.as_view(), name="hours"),
    path(
        "bookings/<uuid:booking_id>/hours/check/",
        views.HoursCheckView.as_view(),
        name="hours-check",
    ),
    path("attendance/keys/", views.KeysView.as_view(), name="keys"),
    path("attendance/arrivals/", views.ArrivalsView.as_view(), name="arrivals"),
    path("attendance/check-ins/", views.CheckInView.as_view(), name="check-in"),
    path("attendance/sync/", views.SyncView.as_view(), name="sync"),
    path("attendance/hours/pending/", views.PendingHoursView.as_view(), name="hours-pending"),
    path("hours/<uuid:log_id>/review/", views.HourReviewView.as_view(), name="hours-review"),
    path("admin/attendance/flagged/", views.FlaggedView.as_view(), name="flagged"),
    path(
        "admin/attendance/<uuid:check_in_id>/review/",
        views.FlagReviewView.as_view(),
        name="flag-review",
    ),
]
