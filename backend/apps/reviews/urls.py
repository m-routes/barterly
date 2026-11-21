from django.urls import path

from apps.reviews import views

app_name = "reviews"

urlpatterns = [
    path("bookings/<uuid:booking_id>/reviews/", views.BookingReviewsView.as_view(), name="booking"),
    path("users/<uuid:user_id>/reviews/", views.UserReviewsView.as_view(), name="of-user"),
    path("users/<uuid:user_id>/reputation/", views.ReputationView.as_view(), name="reputation"),
    path("reviews/<uuid:review_id>/reply/", views.ReplyView.as_view(), name="reply"),
    path("reviews/<uuid:review_id>/report/", views.ReportView.as_view(), name="report"),
    path("admin/reviews/queue/", views.QueueView.as_view(), name="queue"),
    path(
        "admin/reviews/<uuid:review_id>/moderate/",
        views.ModerateView.as_view(),
        name="moderate",
    ),
]
