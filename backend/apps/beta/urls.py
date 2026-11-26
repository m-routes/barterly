from django.urls import path

from apps.beta.views import BetaRulesView

app_name = "beta"

urlpatterns = [path("beta/", BetaRulesView.as_view(), name="rules")]
