from django.urls import path

from apps.analytics.views import EventBatchView

app_name = "analytics"

urlpatterns = [path("analytics/events/", EventBatchView.as_view(), name="events")]
