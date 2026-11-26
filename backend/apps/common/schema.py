"""OpenAPI schema generation tweaks.

drf-spectacular leaves out a few limits the serializers enforce, so the published
schema looked unbounded where the API isn't. This class puts them back:

- `max_length` / `min_length` on a nested serializer with many=True → maxItems/minItems
- the same on a many-related field (see `bounded_slugs`) → maxItems
- a SlugRelatedField's string → maxLength of the model's slug column
"""

from drf_spectacular.openapi import AutoSchema
from rest_framework import serializers


class BarterlyAutoSchema(AutoSchema):
    def _map_serializer_field(self, field, direction, bypass_extensions=False):
        schema = super()._map_serializer_field(field, direction, bypass_extensions)
        if not isinstance(schema, dict):
            return schema
        if schema.get("type") == "array":
            max_items = getattr(field, "max_length", None)
            min_items = getattr(field, "min_length", None)
            if max_items is not None:
                schema.setdefault("maxItems", max_items)
            if min_items is not None:
                schema.setdefault("minItems", min_items)
        if isinstance(field, serializers.SlugRelatedField) and schema.get("type") == "string":
            queryset = field.queryset if field.queryset is not None else None
            if queryset is not None:
                column = queryset.model._meta.get_field(field.slug_field)
                if getattr(column, "max_length", None):
                    schema.setdefault("maxLength", column.max_length)
        return schema
