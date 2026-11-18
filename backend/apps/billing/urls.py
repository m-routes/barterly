from django.urls import path

from apps.billing import views

app_name = "billing"

urlpatterns = [
    path("billing/plans/", views.PlansView.as_view(), name="plans"),
    path("billing/", views.OverviewView.as_view(), name="overview"),
    path("billing/subscribe/", views.SubscribeView.as_view(), name="subscribe"),
    path("billing/change-plan/", views.ChangePlanView.as_view(), name="change-plan"),
    path("billing/cancel/", views.CancelView.as_view(), name="cancel"),
    path("billing/invoices/", views.InvoicesView.as_view(), name="invoices"),
    path(
        "billing/invoices/<uuid:invoice_id>/pdf/",
        views.InvoicePdfView.as_view(),
        name="invoice-pdf",
    ),
    path(
        "billing/webhooks/razorpay/",
        views.RazorpayWebhookView.as_view(),
        name="razorpay-webhook",
    ),
]
