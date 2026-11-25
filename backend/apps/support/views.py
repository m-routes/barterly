from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.bookings.models import Booking
from apps.common.serializers import ErrorSerializer
from apps.support import services
from apps.support.models import Ticket
from apps.support.serializers import (
    OpenSupportTicketSerializer,
    SupportReplySerializer,
    SupportTicketDetailSerializer,
    SupportTicketSerializer,
)

TAG = ["support"]


class SupportThrottle(UserRateThrottle):
    scope = "support"


class SupportRefused(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "support_refused"


def refuse(exc: services.SupportError):
    error = SupportRefused(exc.message, exc.code)
    error.status_code = exc.status
    return error


class TicketListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportTicketSerializer

    def get_throttles(self):
        return [SupportThrottle()] if self.request.method == "POST" else super().get_throttles()

    def get_queryset(self):
        return Ticket.objects.filter(user=self.request.user).order_by("-last_message_at")

    @extend_schema(
        operation_id="support_tickets_list",
        summary="My help and feedback requests",
        responses={200: SupportTicketSerializer(many=True)},
        tags=TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="support_tickets_create",
        summary="Ask for help or send feedback",
        description=(
            "Opens a request in the support inbox. Safety and money requests are urgent "
            "(answered within 2 hours, 8am to 10pm IST); others within a day; feedback "
            "within 3 days. `reply_expected_by` says when."
        ),
        request=OpenSupportTicketSerializer,
        responses={201: SupportTicketDetailSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = OpenSupportTicketSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        booking = None
        if data.get("booking_id"):
            booking = Booking.objects.filter(pk=data["booking_id"]).first()
            if booking is None:
                raise exceptions.NotFound("That booking isn't one of yours.")
        try:
            ticket = services.open_ticket(
                request.user,
                kind=data["kind"],
                subject=data["subject"],
                body=data["body"],
                booking=booking,
                screen=data.get("screen", ""),
                platform=data.get("platform", ""),
                app_version=data.get("app_version", ""),
                request=request,
            )
        except services.SupportError as exc:
            raise refuse(exc) from exc
        return Response(SupportTicketDetailSerializer(ticket).data, status=status.HTTP_201_CREATED)


class TicketDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SupportTicketDetailSerializer
    lookup_url_kwarg = "ticket_id"

    def get_queryset(self):
        return Ticket.objects.filter(user=self.request.user)

    @extend_schema(
        operation_id="support_tickets_retrieve",
        summary="One request with its messages",
        responses={200: SupportTicketDetailSerializer, 404: ErrorSerializer},
        tags=TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class TicketReplyView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [SupportThrottle]

    @extend_schema(
        operation_id="support_tickets_reply",
        summary="Add a message to my request",
        description="A resolved request opens again when the person writes.",
        request=SupportReplySerializer,
        responses={201: SupportTicketDetailSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
        tags=TAG,
    )
    def post(self, request: Request, ticket_id) -> Response:
        ticket = generics.get_object_or_404(Ticket.objects.filter(user=request.user), pk=ticket_id)
        serializer = SupportReplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.reply_as_user(
            ticket, user=request.user, body=serializer.validated_data["body"], request=request
        )
        ticket.refresh_from_db()
        return Response(SupportTicketDetailSerializer(ticket).data, status=status.HTTP_201_CREATED)
