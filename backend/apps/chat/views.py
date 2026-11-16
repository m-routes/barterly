"""Chat over plain REST: send with POST, poll for messages after a cursor while a chat
screen is open. Clients hide this behind a transport interface, so it can move to
WebSockets later without changing their screens."""

from django.db.models import Max
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.chat import services
from apps.chat.models import Conversation, Message
from apps.chat.serializers import (
    ConversationDetailSerializer,
    ConversationSerializer,
    MessagePageSerializer,
    ReadResultSerializer,
    ReadSerializer,
    ReportResultSerializer,
    ReportSerializer,
    SendSerializer,
    SentSerializer,
    UnreadSerializer,
)
from apps.chat.throttles import ChatSendThrottle
from apps.common.permissions import IsVendor
from apps.common.serializers import ErrorSerializer

TAG = ["chat"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


class ChatRefused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "chat_refused"


def refuse(exc: services.ChatError):
    error = ChatRefused(str(exc), code=exc.code)
    error.status_code = exc.status
    return error


def member_conversation(user, conversation_id) -> Conversation:
    return generics.get_object_or_404(services.conversations_for(user), pk=conversation_id)


class ConversationListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConversationSerializer

    def get_queryset(self):
        return services.conversations_for(self.request.user).order_by(
            "-last_message_at", "-opened_at"
        )

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context.update(getattr(self, "_extra", {}))
        return context

    def paginate_queryset(self, queryset):
        page = super().paginate_queryset(queryset)
        rows = page if page is not None else list(queryset)
        ids = [c.pk for c in rows]
        user = self.request.user
        latest = (
            Message.objects.filter(conversation_id__in=ids)
            .values("conversation_id")
            .annotate(seq=Max("seq"))
        )
        wanted = {(r["conversation_id"], r["seq"]) for r in latest}
        last = {
            m.conversation_id: m
            for m in Message.objects.filter(conversation_id__in=ids, seq__in={s for _, s in wanted})
            if (m.conversation_id, m.seq) in wanted
        }
        self._extra = {"unread": services.unread_by_conversation(user, ids), "last": last}
        return page

    @extend_schema(
        operation_id="chat_conversations_list",
        summary="My conversations, newest first, with unread counts",
        tags=TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class UnreadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="chat_unread",
        summary="Unread message count (for a badge)",
        responses={200: UnreadSerializer, 401: ErrorSerializer},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(UnreadSerializer(services.unread_total(request.user)).data)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="chat_conversation_detail",
        summary="One conversation: who, whether you can send, whether contacts are hidden",
        responses={200: ConversationDetailSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, conversation_id) -> Response:
        conversation = member_conversation(request.user, conversation_id)
        return Response(
            ConversationDetailSerializer(conversation, context={"request": request}).data
        )


class OpenConversationView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="chat_open",
        summary="Open (or get) the chat with an applicant",
        description="Vendors only. Talent can reply once the vendor has shortlisted or "
        "messaged them. Returns 201 when the conversation is new.",
        request=None,
        responses={200: ConversationDetailSerializer, 201: ConversationDetailSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        before = Conversation.objects.filter(application_id=application_id).exists()
        try:
            conversation = services.vendor_open(
                application_id, vendor=request.user, request=request
            )
        except services.ChatError as exc:
            raise refuse(exc) from exc
        conversation = member_conversation(request.user, conversation.pk)
        data = ConversationDetailSerializer(conversation, context={"request": request}).data
        return Response(data, status=status.HTTP_200_OK if before else status.HTTP_201_CREATED)


class MessagesView(APIView):
    permission_classes = [IsAuthenticated]

    def get_throttles(self):
        return [ChatSendThrottle()] if self.request.method == "POST" else []

    @extend_schema(
        operation_id="chat_messages_list",
        summary="Messages after a cursor (polling), before one (history), or the newest",
        description=(
            "Poll with `after=<cursor>` every few seconds while the chat is open; the "
            "answer's `cursor` is the next `after`. Without `after`, returns the newest "
            "page; `before=<cursor>` pages back through history."
        ),
        parameters=[
            OpenApiParameter("after", str, description="Only messages after this cursor."),
            OpenApiParameter("before", str, description="Only messages before this cursor."),
            OpenApiParameter("limit", int, description="Default 50, at most 100."),
        ],
        responses={200: MessagePageSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, conversation_id) -> Response:
        conversation = member_conversation(request.user, conversation_id)
        params = request.query_params
        try:
            page = services.fetch(
                conversation,
                request.user,
                after=params.get("after"),
                before=params.get("before"),
                limit=params.get("limit") if str(params.get("limit", "")).isdigit() else None,
            )
        except services.ChatError as exc:
            raise refuse(exc) from exc
        return Response(MessagePageSerializer(page, context={"request": request}).data)

    @extend_schema(
        operation_id="chat_messages_send",
        summary="Send a message",
        description=(
            "Before the booking is confirmed, phone numbers, emails, links, handles and "
            "off-platform contact phrases are replaced with [hidden]; `notice` says so. "
            "Rate limited (429). 403 when the chat is closed or a block is in place."
        ),
        request=SendSerializer,
        responses={201: SentSerializer, 400: ErrorSerializer, 429: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, conversation_id) -> Response:
        member_conversation(request.user, conversation_id)
        serializer = SendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            sent = services.send(
                conversation_id,
                sender=request.user,
                body=data.get("body", ""),
                attachment_ids=data.get("attachment_ids", []),
                client_id=data.get("client_id", ""),
                request=request,
            )
        except services.ChatError as exc:
            raise refuse(exc) from exc
        body = SentSerializer(
            {"message": sent.message, "notice": sent.notice}, context={"request": request}
        ).data
        return Response(body, status=status.HTTP_201_CREATED)


class ReadView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="chat_mark_read",
        summary="Mark the other side's messages read, up to a cursor",
        request=ReadSerializer,
        responses={200: ReadResultSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, conversation_id) -> Response:
        conversation = member_conversation(request.user, conversation_id)
        serializer = ReadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            marked = services.mark_read(
                conversation, request.user, serializer.validated_data["up_to"]
            )
        except services.ChatError as exc:
            raise refuse(exc) from exc
        return Response({"marked": marked})


class BlockView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="chat_block",
        summary="Block the other person in this conversation",
        description="Neither side can send while the block is in place.",
        request=None,
        responses={200: ConversationDetailSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, conversation_id) -> Response:
        conversation = member_conversation(request.user, conversation_id)
        services.block(conversation, request.user, request=request)
        return Response(
            ConversationDetailSerializer(conversation, context={"request": request}).data
        )

    @extend_schema(
        operation_id="chat_unblock",
        summary="Unblock the other person",
        responses={200: ConversationDetailSerializer, **ERRORS},
        tags=TAG,
    )
    def delete(self, request: Request, conversation_id) -> Response:
        conversation = member_conversation(request.user, conversation_id)
        services.unblock(conversation, request.user, request=request)
        return Response(
            ConversationDetailSerializer(conversation, context={"request": request}).data
        )


class ReportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="chat_report",
        summary="Report a message for review",
        request=ReportSerializer,
        responses={
            201: ReportResultSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, message_id) -> Response:
        serializer = ReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            created = services.report(
                message_id, reporter=request.user, request=request, **serializer.validated_data
            )
        except services.ChatError as exc:
            raise refuse(exc) from exc
        return Response(
            {"id": created.pk, "status": created.status}, status=status.HTTP_201_CREATED
        )
