from rest_framework import serializers


class ErrorSerializer(serializers.Serializer):
    """Shape of every error response. Use it in extend_schema(responses=...)."""

    code = serializers.CharField(help_text="Stable machine-readable code, e.g. 'not_found'.")
    message = serializers.CharField()
    details = serializers.DictField(
        help_text="Extra context. Field errors for 'validation_error'; otherwise often empty."
    )


class BoundedManyRelatedField(serializers.ManyRelatedField):
    """A many-related field that refuses more than `max_length` items.

    The limit is a constructor argument so it survives DRF's deepcopy of declared
    fields; the schema reports it as maxItems (apps.common.schema).
    """

    def __init__(self, child_relation=None, *args, max_length: int | None = None, **kwargs):
        self.max_length = max_length
        super().__init__(child_relation, *args, **kwargs)

    def to_internal_value(self, data):
        if self.max_length is not None and isinstance(data, list) and len(data) > self.max_length:
            raise serializers.ValidationError(f"Pick at most {self.max_length}.")
        return super().to_internal_value(data)


def bounded_slugs(max_items: int, **kwargs) -> BoundedManyRelatedField:
    """SlugRelatedField(many=True, ...) with at most `max_items` slugs."""
    from rest_framework.relations import MANY_RELATION_KWARGS

    list_kwargs = {k: v for k, v in kwargs.items() if k in MANY_RELATION_KWARGS}
    child = serializers.SlugRelatedField(**kwargs)
    return BoundedManyRelatedField(child_relation=child, max_length=max_items, **list_kwargs)
