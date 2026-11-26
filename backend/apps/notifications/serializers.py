from rest_framework import serializers

from apps.notifications import catalog
from apps.notifications.models import Channel, DevicePlatform, Locale, Notification


class NotificationSerializer(serializers.ModelSerializer):
    read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "title",
            "body",
            "urgent",
            "app_path",
            "web_url",
            "read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_read(self, notification) -> bool:
        return notification.read_at is not None


class UnreadCountSerializer(serializers.Serializer):
    unread = serializers.IntegerField()


class MarkReadSerializer(serializers.Serializer):
    from_push = serializers.BooleanField(
        default=False, help_text="Opened by tapping the push: the push counts as read too."
    )


class MarkedSerializer(serializers.Serializer):
    marked = serializers.IntegerField()


class ChannelSettingSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    locked = serializers.BooleanField(help_text="In-app can't be switched off: it's the inbox.")


class EventTypeSettingSerializer(serializers.Serializer):
    key = serializers.CharField()
    label = serializers.CharField()
    urgent = serializers.BooleanField(help_text="Not held back by quiet hours.")
    channels = serializers.DictField(child=ChannelSettingSerializer())


class PreferencesSerializer(serializers.Serializer):
    locale = serializers.ChoiceField(choices=Locale.choices)
    quiet_hours_enabled = serializers.BooleanField()
    quiet_start = serializers.TimeField(format="%H:%M", help_text="India time.")
    quiet_end = serializers.TimeField(format="%H:%M", help_text="India time.")
    channels_available = serializers.ListField(
        child=serializers.ChoiceField(choices=Channel.choices),
        help_text="Channels Barterly can send on right now.",
    )
    event_types = EventTypeSettingSerializer(many=True)


class PreferenceChangeSerializer(serializers.Serializer):
    event_type = serializers.ChoiceField(
        choices=[t.key for t in catalog.FEATURED if t.configurable]
    )
    channel = serializers.ChoiceField(choices=Channel.choices)
    enabled = serializers.BooleanField()


class UpdatePreferencesSerializer(serializers.Serializer):
    locale = serializers.ChoiceField(choices=Locale.choices, required=False)
    quiet_hours_enabled = serializers.BooleanField(required=False)
    quiet_start = serializers.TimeField(required=False)
    quiet_end = serializers.TimeField(required=False)
    changes = PreferenceChangeSerializer(many=True, required=False, max_length=100)


class DeviceSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)
    platform = serializers.ChoiceField(choices=DevicePlatform.choices)


class DeviceTokenSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)
