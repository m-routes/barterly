from rest_framework import serializers

from apps.reliability.models import Side
from apps.reliability.score import LEVELS, NEW


class ReliabilitySerializer(serializers.Serializer):
    score = serializers.IntegerField(min_value=0, max_value=100)
    level = serializers.ChoiceField(choices=[NEW, *(name for _, name in LEVELS)])
    version = serializers.CharField()


class ReliabilityDetailSerializer(ReliabilitySerializer):
    side = serializers.ChoiceField(choices=Side.choices)
    inputs = serializers.DictField(child=serializers.IntegerField())
    breakdown = serializers.DictField(
        child=serializers.IntegerField(), help_text="Each term's points (docs/reliability.md)."
    )
