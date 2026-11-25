from rest_framework import serializers

from apps.flags.registry import FLAGS


class FlagSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=sorted(FLAGS))
    enabled = serializers.BooleanField()
    description = serializers.CharField()
    when_off = serializers.CharField()


class FlagValuesSerializer(serializers.Serializer):
    """For apps and the web: which risky features are on right now."""

    escrow_funding = serializers.BooleanField()
    sos_live_sharing = serializers.BooleanField()
    ai_safety_checks = serializers.BooleanField()
    closed_beta = serializers.BooleanField()


class SetFlagSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    reason = serializers.CharField(max_length=300)
