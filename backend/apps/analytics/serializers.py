from rest_framework import serializers

from apps.analytics.events import EVENTS
from apps.analytics.models import Platform


class AnalyticsEventSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=40, help_text=f"One of: {', '.join(sorted(EVENTS))}.")
    occurred_at = serializers.CharField(
        max_length=40,
        required=False,
        help_text="ISO 8601 with an offset; up to 7 days old. Default: now.",
    )
    props = serializers.DictField(
        required=False, help_text="Only the properties listed for the event are kept."
    )


class AnalyticsEventBatchSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=Platform.choices)
    app_version = serializers.CharField(max_length=20, required=False, allow_blank=True)
    events = AnalyticsEventSerializer(many=True, max_length=50)


class AnalyticsEventBatchResultSerializer(serializers.Serializer):
    accepted = serializers.IntegerField()
    dropped = serializers.IntegerField()
    consent = serializers.BooleanField(
        help_text="False: the person hasn't agreed to analytics, so nothing was kept. "
        "Clients should stop sending until they do."
    )
