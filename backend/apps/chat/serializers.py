from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.applications.constants import ApplicationStatus
from apps.chat import services
from apps.chat.models import MAX_ATTACHMENTS, MAX_BODY, Conversation, Message, ReportReason
from apps.media.policy import IMAGE_TYPES
from apps.media.services.uploads import read_urls


class ChatAttachmentSerializer(serializers.Serializer):
    id = serializers.UUIDField(source="media_id")
    kind = serializers.SerializerMethodField()
    content_type = serializers.CharField(source="media.content_type")
    size_bytes = serializers.IntegerField(source="media.size_bytes")
    url = serializers.SerializerMethodField(help_text="Signed and short-lived.")
    thumb_url = serializers.SerializerMethodField()

    def get_kind(self, attachment) -> str:
        return "image" if attachment.media.content_type in IMAGE_TYPES else "document"

    def _urls(self, attachment) -> dict:
        cache = self.context.setdefault("_urls", {})
        if attachment.media_id not in cache:
            cache[attachment.media_id] = read_urls(attachment.media)
        return cache[attachment.media_id]

    def get_url(self, attachment) -> str | None:
        return self._urls(attachment)["url"]

    def get_thumb_url(self, attachment) -> str | None:
        return self._urls(attachment)["variants"].get("thumb")


class ChatMessageSerializer(serializers.ModelSerializer):
    cursor = serializers.CharField(source="seq", help_text="This message's place; ascending.")
    mine = serializers.SerializerMethodField()
    attachments = ChatAttachmentSerializer(many=True, read_only=True)
    masked = serializers.SerializerMethodField(
        help_text="True when contact details in it were hidden."
    )

    class Meta:
        model = Message
        fields = [
            "id",
            "cursor",
            "sender",
            "mine",
            "body",
            "masked",
            "attachments",
            "client_id",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_mine(self, message) -> bool:
        return message.sender_id == self.context["request"].user.pk

    def get_masked(self, message) -> bool:
        return bool(message.masked_kinds)


class SendSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=MAX_BODY, required=False, allow_blank=True)
    attachment_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        max_length=MAX_ATTACHMENTS,
        help_text="Confirmed uploads (kind 'photo' or 'document'): JPEG, PNG, WebP or PDF, "
        "up to 10 MB each.",
    )
    client_id = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        help_text="Your id for this send; sending again with it returns the same message.",
    )


class SentSerializer(serializers.Serializer):
    message = ChatMessageSerializer()
    notice = serializers.CharField(
        help_text="Tell the sender this when it isn't empty (e.g. why a number was hidden)."
    )


class MessagePageSerializer(serializers.Serializer):
    results = ChatMessageSerializer(many=True, source="messages")
    cursor = serializers.CharField(help_text="Send as `after` on the next poll.")
    has_earlier = serializers.BooleanField(help_text="Older messages exist (use `before`).")
    other_read_up_to = serializers.CharField(
        help_text="The newest of your messages the other side has read (a cursor)."
    )


class ReadSerializer(serializers.Serializer):
    up_to = serializers.CharField(
        max_length=200, help_text="A message cursor; everything up to it is read."
    )


class ReadResultSerializer(serializers.Serializer):
    marked = serializers.IntegerField()


class ReportSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=ReportReason.choices)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ReportResultSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    status = serializers.CharField()


class PartySerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    role = serializers.CharField()


class LastMessageSerializer(serializers.Serializer):
    body = serializers.CharField()
    mine = serializers.BooleanField()
    created_at = serializers.DateTimeField()


class ConversationSerializer(serializers.ModelSerializer):
    application = serializers.UUIDField(source="application_id")
    gig_title = serializers.CharField(source="application.gig.title")
    application_status = serializers.ChoiceField(
        source="application.status", choices=ApplicationStatus.choices
    )
    other = serializers.SerializerMethodField()
    unread = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "application",
            "gig_title",
            "application_status",
            "other",
            "unread",
            "last_message",
            "last_message_at",
            "opened_at",
        ]
        read_only_fields = fields

    def _me(self):
        return self.context["request"].user

    @extend_schema_field(PartySerializer)
    def get_other(self, conversation):
        other = conversation.other(self._me())
        return {"id": other.pk, "name": services.display_name(other), "role": other.role}

    def get_unread(self, conversation) -> int:
        counts = self.context.get("unread")
        if counts is None:
            counts = services.unread_by_conversation(self._me(), [conversation.pk])
        return counts.get(conversation.pk, 0)

    @extend_schema_field(LastMessageSerializer(allow_null=True))
    def get_last_message(self, conversation):
        last = self.context.get("last", {}).get(conversation.pk)
        if last is None and "last" not in self.context:
            last = conversation.messages.order_by("-seq").first()
        if last is None:
            return None
        body = last.body or "Sent an attachment"
        return {
            "body": body[: services.PREVIEW],
            "mine": last.sender_id == self._me().pk,
            "created_at": last.created_at,
        }


class ConversationDetailSerializer(ConversationSerializer):
    can_send = serializers.SerializerMethodField()
    cant_send_reason = serializers.SerializerMethodField()
    contact_sharing_allowed = serializers.SerializerMethodField(
        help_text="False until the booking is confirmed: contact details get hidden."
    )
    blocked_by_me = serializers.SerializerMethodField()

    class Meta(ConversationSerializer.Meta):
        fields = [
            *ConversationSerializer.Meta.fields,
            "can_send",
            "cant_send_reason",
            "contact_sharing_allowed",
            "blocked_by_me",
        ]
        read_only_fields = fields

    def get_can_send(self, conversation) -> bool:
        return not services.why_cant_send(conversation, self._me())

    def get_cant_send_reason(self, conversation) -> str:
        return services.why_cant_send(conversation, self._me())

    def get_contact_sharing_allowed(self, conversation) -> bool:
        return services.contact_sharing_allowed(conversation)

    def get_blocked_by_me(self, conversation) -> bool:
        return services.blocked_by(self._me(), conversation.other(self._me()))


class UnreadSerializer(serializers.Serializer):
    unread = serializers.IntegerField(help_text="Unread messages across all conversations.")
    conversations = serializers.IntegerField(help_text="Conversations with unread messages.")
