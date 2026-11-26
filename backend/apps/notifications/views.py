from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.serializers import ErrorSerializer
from apps.notifications import catalog, services
from apps.notifications.channels.base import available
from apps.notifications.models import (
    Channel,
    Notification,
    NotificationPreference,
    NotificationSettings,
    PushDevice,
)
from apps.notifications.serializers import (
    DeviceSerializer,
    DeviceTokenSerializer,
    MarkedSerializer,
    MarkReadSerializer,
    NotificationSerializer,
    PreferencesSerializer,
    UnreadCountSerializer,
    UpdatePreferencesSerializer,
)

TAG = ["notifications"]
ERRORS = {401: ErrorSerializer, 404: ErrorSerializer}


class InboxView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = NotificationSerializer

    def get_queryset(self):
        qs = Notification.objects.filter(user=self.request.user)
        if self.request.query_params.get("unread") in ("1", "true"):
            qs = qs.filter(read_at__isnull=True)
        return qs.order_by("-created_at")

    @extend_schema(
        operation_id="notifications_list",
        summary="My notifications, newest first",
        parameters=[OpenApiParameter("unread", bool, description="Only unread ones.")],
        responses={200: NotificationSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class UnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="notifications_unread_count",
        summary="How many notifications I haven't read",
        responses={200: UnreadCountSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        count = Notification.objects.filter(user=request.user, read_at__isnull=True).count()
        return Response({"unread": count})


class MarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="notifications_read",
        summary="Mark one notification read",
        request=MarkReadSerializer,
        responses={200: NotificationSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, notification_id) -> Response:
        notification = generics.get_object_or_404(
            Notification.objects.filter(user=request.user), pk=notification_id
        )
        serializer = MarkReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.mark_read(
            request.user, [notification.pk], from_push=serializer.validated_data["from_push"]
        )
        notification.refresh_from_db()
        return Response(NotificationSerializer(notification).data)


class MarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="notifications_read_all",
        summary="Mark every notification read",
        request=None,
        responses={200: MarkedSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        return Response({"marked": services.mark_read(request.user)})


def preferences_for(user) -> dict:
    prefs = services.settings_for(user)
    overrides = services.overrides_for(user)
    locale = prefs.locale
    channels_available = [c for c in Channel.values if c == Channel.IN_APP or available(c)]
    event_types = []
    for t in catalog.FEATURED:
        on = catalog.enabled_channels(t.key, overrides)
        event_types.append(
            {
                "key": t.key,
                "label": t.label_hi if locale == "hi" else t.label_en,
                "urgent": t.urgent or t.key in catalog.URGENT_EVENTS,
                "channels": {
                    c: {"enabled": c in on, "locked": c == Channel.IN_APP or not t.configurable}
                    for c in channels_available
                },
            }
        )
    return {
        "locale": locale,
        "quiet_hours_enabled": prefs.quiet_hours_enabled,
        "quiet_start": prefs.quiet_start,
        "quiet_end": prefs.quiet_end,
        "channels_available": channels_available,
        "event_types": event_types,
    }


class PreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="notifications_preferences",
        summary="What I'm notified about, on which channels, and quiet hours",
        responses={200: PreferencesSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(PreferencesSerializer(preferences_for(request.user)).data)

    @extend_schema(
        operation_id="notifications_preferences_update",
        summary="Change language, quiet hours or channels per event type",
        description=(
            "Send only what changes. `changes` switches one event type on one channel. "
            "In-app can't be switched off. Urgent reminders (an offer about to expire, an "
            "interview within the hour) ignore quiet hours."
        ),
        request=UpdatePreferencesSerializer,
        responses={200: PreferencesSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def put(self, request: Request) -> Response:
        serializer = UpdatePreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        prefs, _ = NotificationSettings.objects.get_or_create(user=request.user)
        for field in ("locale", "quiet_hours_enabled", "quiet_start", "quiet_end"):
            if field in data:
                setattr(prefs, field, data[field])
        prefs.save()
        for change in data.get("changes", []):
            if change["channel"] == Channel.IN_APP:
                continue
            NotificationPreference.objects.update_or_create(
                user=request.user,
                event_type=change["event_type"],
                channel=change["channel"],
                defaults={"enabled": change["enabled"]},
            )
        return Response(PreferencesSerializer(preferences_for(request.user)).data)


class DeviceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="notifications_devices_register",
        summary="Register this device for push (an FCM token)",
        description="A token already registered moves to whoever registers it last.",
        request=DeviceSerializer,
        responses={204: None, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = DeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PushDevice.objects.update_or_create(
            token=serializer.validated_data["token"],
            defaults={
                "user": request.user,
                "platform": serializer.validated_data["platform"],
                "last_seen_at": timezone.now(),
                "disabled_at": None,
            },
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DeviceRemoveView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="notifications_devices_remove",
        summary="Stop push to this device (on sign-out)",
        request=DeviceTokenSerializer,
        responses={204: None, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = DeviceTokenSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        PushDevice.objects.filter(
            user=request.user, token=serializer.validated_data["token"]
        ).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
