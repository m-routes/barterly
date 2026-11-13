from rest_framework import serializers


class ErrorSerializer(serializers.Serializer):
    """Shape of every error response. Use it in extend_schema(responses=...)."""

    code = serializers.CharField(help_text="Stable machine-readable code, e.g. 'not_found'.")
    message = serializers.CharField()
    details = serializers.DictField(
        help_text="Extra context. Field errors for 'validation_error'; otherwise often empty."
    )
