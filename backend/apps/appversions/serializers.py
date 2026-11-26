from rest_framework import serializers

from apps.appversions.models import Platform


class AppVersionSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=Platform.choices)
    minimum_version = serializers.CharField(
        help_text="Older apps get 426 upgrade_required on every call."
    )
    latest_version = serializers.CharField(help_text="Older apps are offered an update.")
    store_url = serializers.CharField(help_text="Where the update button goes. May be empty.")
    message = serializers.CharField(help_text="Shown on the update screen. May be empty.")


class AppVersionStatusSerializer(AppVersionSerializer):
    update = serializers.ChoiceField(
        choices=["required", "available", "none"],
        help_text="For the `version` asked about; `none` when no version was given.",
    )


class AppVersionQuerySerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=Platform.choices)
    version = serializers.CharField(required=False, max_length=40)


class SetAppVersionSerializer(serializers.Serializer):
    minimum_version = serializers.CharField(max_length=20)
    latest_version = serializers.CharField(max_length=20)
    store_url = serializers.URLField(max_length=300, required=False, allow_blank=True)
    message = serializers.CharField(max_length=300, required=False, allow_blank=True)
    reason = serializers.CharField(max_length=300)
