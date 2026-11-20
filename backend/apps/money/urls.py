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
    path("money/webhooks/razorpayx/", views.PayoutWebhookView.as_view(), name="payout-webhook"),
    path("payout-account/", views.PayoutAccountView.as_view(), name="payout-account"),
    path("wallet/", views.WalletView.as_view(), name="wallet"),
    path("wallet/history/", views.WalletHistoryView.as_view(), name="wallet-history"),
    path("wallet/payout/", views.WalletPayoutView.as_view(), name="wallet-payout"),
    path("wallet/statements/<str:fy>/", views.StatementView.as_view(), name="statement"),
    path(
        "wallet/statements/<str:fy>/<str:kind>/",
        views.StatementFileView.as_view(),
        name="statement-file",
    ),
    path("wallet/tds/<str:fy>/", views.TdsView.as_view(), name="tds"),
    path("wallet/tds/<str:fy>/<str:kind>/", views.TdsFileView.as_view(), name="tds-file"),
    path("admin/money/payout-runs/", views.PayoutRunsView.as_view(), name="payout-runs"),
    path(
        "admin/money/payout-runs/<int:run_id>/",
        views.PayoutRunDetailView.as_view(),
        name="payout-run",
    ),
    path("admin/money/payouts/", views.PayoutsAdminView.as_view(), name="payouts"),
    path(
        "admin/money/payouts/<uuid:payout_id>/retry/",
        views.PayoutRetryView.as_view(),
        name="payout-retry",
    ),
]
