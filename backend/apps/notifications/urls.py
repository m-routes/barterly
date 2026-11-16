from django.urls import path

from apps.notifications import views

app_name = "notifications"

urlpatterns = [
    path("notifications/", views.InboxView.as_view(), name="list"),
    path("notifications/unread-count/", views.UnreadCountView.as_view(), name="unread-count"),
    path("notifications/read-all/", views.MarkAllReadView.as_view(), name="read-all"),
    path("notifications/preferences/", views.PreferencesView.as_view(), name="preferences"),
    path("notifications/devices/", views.DeviceView.as_view(), name="devices"),
    path("notifications/devices/remove/", views.DeviceRemoveView.as_view(), name="devices-remove"),
    path(
        "notifications/<uuid:notification_id>/read/",
        views.MarkReadView.as_view(),
        name="read",
    ),
]
