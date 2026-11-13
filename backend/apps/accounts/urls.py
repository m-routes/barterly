from django.urls import path

from apps.accounts.views import ExchangeView, LogoutView, MeRoleView, MeView, RefreshView

app_name = "accounts"

urlpatterns = [
    path("auth/exchange/", ExchangeView.as_view(), name="auth-exchange"),
    path("auth/refresh/", RefreshView.as_view(), name="auth-refresh"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/role/", MeRoleView.as_view(), name="me-role"),
]
