from django.urls import path

from apps.money import views

app_name = "money"

urlpatterns = [
    path("bookings/<uuid:booking_id>/escrow/", views.EscrowView.as_view(), name="escrow"),
    path("bookings/<uuid:booking_id>/escrow/fund/", views.FundView.as_view(), name="fund"),
    path(
        "bookings/<uuid:booking_id>/deliverables/",
        views.DeliverablesView.as_view(),
        name="deliverables",
    ),
    path(
        "deliverables/<uuid:submission_id>/review/",
        views.ReviewDeliverableView.as_view(),
        name="review",
    ),
    path(
        "admin/money/escrows/<uuid:booking_id>/decide/",
        views.DecideView.as_view(),
        name="decide",
    ),
    path("admin/money/kill-switch/", views.KillSwitchView.as_view(), name="kill-switch"),
    path(
        "admin/money/reconciliation/",
        views.ReconciliationView.as_view(),
        name="reconciliation",
    ),
    path("money/webhooks/razorpay/", views.WebhookView.as_view(), name="webhook"),
]
