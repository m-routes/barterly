from django.urls import path

from apps.core.views import HealthView

app_name = "core"

# Cloud Run reserves some paths ending in "z", so the probe path is /api/v1/health/.
urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
]
