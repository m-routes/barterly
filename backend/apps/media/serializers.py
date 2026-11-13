from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.media.models import MediaFile
from apps.media.policy import EXTENSIONS, Kind
from apps.media.services.uploads import read_urls


class UploadUrlRequestSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=Kind.choices)
    content_type = serializers.ChoiceField(choices=sorted(EXTENSIONS))
    size_bytes = serializers.IntegerField(min_value=1)
    checksum_md5 = serializers.RegexField(
        r"^[0-9a-fA-F]{32}$",
        required=False,
        allow_blank=True,
        help_text="Optional hex MD5. If sent, Cloud Storage rejects a body that doesn't match.",
    )


class UploadUrlResponseSerializer(serializers.Serializer):
    media_id = serializers.UUIDField()
    upload_url = serializers.URLField()
    method = serializers.CharField()
    headers = serializers.DictField(
        child=serializers.CharField(), help_text="Send exactly these headers with the upload."
    )
    expires_at = serializers.DateTimeField()


class ConfirmRequestSerializer(serializers.Serializer):
    media_id = serializers.UUIDField()


class MediaFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField(help_text="Signed, short-lived; null until ready.")
    variants = serializers.SerializerMethodField(
        help_text="Signed URLs for resized copies (images only)."
    )
    url_expires_at = serializers.SerializerMethodField()

    class Meta:
        model = MediaFile
        fields = [
            "id",
            "kind",
            "status",
            "content_type",
            "size_bytes",
            "checksum_md5",
            "scan_status",
            "rejection_reason",
            "url",
            "variants",
            "url_expires_at",
            "created_at",
        ]
        read_only_fields = fields

    def _urls(self, media) -> dict:
        cache = self.context.setdefault("_urls", {})
        if media.pk not in cache:
            cache[media.pk] = read_urls(media)
        return cache[media.pk]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_url(self, media):
        return self._urls(media)["url"]

    @extend_schema_field(serializers.DictField(child=serializers.URLField()))
    def get_variants(self, media):
        return self._urls(media)["variants"]

    @extend_schema_field(serializers.DateTimeField(allow_null=True))
    def get_url_expires_at(self, media):
        expires = self._urls(media)["expires_at"]
        return serializers.DateTimeField().to_representation(expires) if expires else None
