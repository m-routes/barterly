from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.applications.constants import MAX_ATTACHMENTS
from apps.applications.models import Application, ApplicationAttachment, AttachmentKind
from apps.discovery.serializers import FitSerializer
from apps.media.services.uploads import read_urls


class AttachmentInputSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=AttachmentKind.choices)
    media_id = serializers.UUIDField(
        required=False, help_text="Your upload (photo, video, document)."
    )
    url = serializers.URLField(required=False, max_length=500, help_text="For kind 'link' only.")
    title = serializers.CharField(max_length=120, required=False, allow_blank=True)

    def validate(self, attrs):
        if attrs["kind"] == AttachmentKind.LINK:
            if not attrs.get("url") or "media_id" in attrs:
                raise serializers.ValidationError("A link needs a url and no media_id.")
            if not attrs["url"].startswith("https://"):
                raise serializers.ValidationError({"url": ["Use an https:// link."]})
        elif not attrs.get("media_id") or attrs.get("url"):
            raise serializers.ValidationError("Uploads need a media_id and no url.")
        return attrs


class ApplySerializer(serializers.Serializer):
    pitch = serializers.CharField(max_length=2000)
    answers = serializers.ListField(
        child=serializers.CharField(max_length=1000, allow_blank=True),
        required=False,
        default=list,
        help_text="One answer per screening question, in order.",
    )
    proposed_start = serializers.DateField()
    proposed_end = serializers.DateField()
    attachments = AttachmentInputSerializer(
        many=True, required=False, default=list, max_length=MAX_ATTACHMENTS
    )


class AttachmentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField(help_text="Signed and short-lived for uploads.")
    thumb_url = serializers.SerializerMethodField()

    class Meta:
        model = ApplicationAttachment
        fields = ["id", "kind", "title", "url", "thumb_url"]
        read_only_fields = fields

    def _urls(self, attachment) -> dict:
        cache = self.context.setdefault("_urls", {})
        if attachment.media_id not in cache:
            cache[attachment.media_id] = read_urls(attachment.media)
        return cache[attachment.media_id]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_url(self, attachment):
        if attachment.kind == AttachmentKind.LINK:
            return attachment.url
        return self._urls(attachment)["url"]

    @extend_schema_field(serializers.URLField(allow_null=True))
    def get_thumb_url(self, attachment):
        if attachment.kind == AttachmentKind.LINK:
            return None
        return self._urls(attachment)["variants"].get("thumb")


class ApplicantSerializer(serializers.Serializer):
    """Who applied. Deliberately no phone, email, emergency contact, birth date or
    social handle: contact happens on Barterly once there's a booking."""

    user_id = serializers.UUIDField()
    display_name = serializers.CharField()
    talent_type = serializers.CharField()
    home_city = serializers.CharField()
    bio = serializers.CharField()
    languages = serializers.ListField(child=serializers.CharField())
    skills = serializers.ListField(child=serializers.CharField())
    instagram_followers = serializers.IntegerField(allow_null=True)
    badges = serializers.ListField(child=serializers.CharField(), help_text="Active badge kinds.")


def applicant(user) -> dict:
    profile = getattr(user, "talent_profile", None)
    return {
        "user_id": user.pk,
        "display_name": profile.display_name if profile else "",
        "talent_type": profile.talent_type if profile else "",
        "home_city": profile.home_city if profile else "",
        "bio": profile.bio if profile else "",
        "languages": (profile.languages or []) if profile else [],
        "skills": [s.slug for s in profile.skills.all()] if profile else [],
        "instagram_followers": profile.instagram_followers if profile else None,
        "badges": sorted(b.kind for b in getattr(user, "active_badges", [])),
    }


class _ApplicationBase(serializers.ModelSerializer):
    gig_title = serializers.CharField(source="gig.title", read_only=True)
    applicant = serializers.SerializerMethodField()
    fit = serializers.SerializerMethodField()

    @extend_schema_field(ApplicantSerializer)
    def get_applicant(self, application):
        return applicant(application.talent)

    @extend_schema_field(FitSerializer)
    def get_fit(self, application):
        return {"score": application.fit_score, "breakdown": application.fit_breakdown}


class ApplicationListItemSerializer(_ApplicationBase):
    attachment_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Application
        fields = [
            "id",
            "gig",
            "gig_title",
            "status",
            "proposed_start",
            "proposed_end",
            "applicant",
            "fit",
            "attachment_count",
            "applied_at",
        ]
        read_only_fields = fields


class ApplicationSerializer(_ApplicationBase):
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Application
        fields = [
            "id",
            "gig",
            "gig_title",
            "status",
            "status_reason",
            "pitch",
            "answers",
            "proposed_start",
            "proposed_end",
            "applicant",
            "fit",
            "attachments",
            "applied_at",
            "decided_at",
        ]
        read_only_fields = fields


class WithdrawSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class BlockedSerializer(serializers.Serializer):
    code = serializers.CharField(default="application_blocked")
    message = serializers.CharField()
    details = serializers.DictField(help_text='{"reasons": [{"code", "message"}, ...]}')
