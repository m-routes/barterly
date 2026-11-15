from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications.models import Application
from apps.bookings import jobs
from apps.bookings.lifecycle import BookingStatus
from apps.bookings.models import Booking
from apps.bookings.scheduler import SchedulerAuthError, verify_request
from apps.bookings.serializers import (
    BookingListItemSerializer,
    BookingSerializer,
    BookingTransitionSerializer,
    JobResultSerializer,
)
from apps.bookings.services import BookingRefused, accept_offer, actor_for, transition
from apps.common.permissions import IsTalent
from apps.common.serializers import ErrorSerializer

TAG = ["bookings"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


class Refused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "That can't happen from the booking's current status."
    default_code = "transition_refused"


def bookings_for(user):
    qs = Booking.objects.select_related("gig").prefetch_related("events")
    if getattr(user, "is_admin_role", False):
        return qs
    return qs.filter(Q(talent=user) | Q(vendor=user))


class AcceptOfferView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="applications_accept",
        summary="Accept an offer",
        description=(
            "Books a slot: the application becomes confirmed and a booking is created. "
            "Refused (409) when the offer has expired, the gig has no slot left, or you "
            "already have a booking for those dates."
        ),
        request=None,
        responses={201: BookingSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        try:
            booking = accept_offer(application_id, talent=request.user, request=request)
        except (Booking.DoesNotExist, Application.DoesNotExist) as exc:
            raise exceptions.NotFound("No such application.") from exc
        except BookingRefused as exc:
            raise Refused(str(exc)) from exc
        booking = bookings_for(request.user).get(pk=booking.pk)
        return Response(
            BookingSerializer(booking, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )


class BookingListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingListItemSerializer

    def get_queryset(self):
        qs = bookings_for(self.request.user).order_by("-confirmed_at")
        wanted = self.request.query_params.get("status")
        return qs.filter(status=wanted) if wanted else qs

    @extend_schema(
        operation_id="bookings_list",
        summary="My bookings",
        description="As talent or as the vendor, newest first.",
        parameters=[OpenApiParameter("status", enum=BookingStatus.values)],
        responses={200: BookingListItemSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class BookingDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = BookingSerializer
    lookup_url_kwarg = "booking_id"

    def get_queryset(self):
        return bookings_for(self.request.user)

    @extend_schema(
        operation_id="bookings_retrieve",
        summary="One booking, with its history",
        responses={200: BookingSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class BookingTransitionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="bookings_transition",
        summary="Move a booking",
        description=(
            "Check in, start delivering, complete, cancel, report a no-show, dispute, "
            "review; admins also resolve disputes and refund. The transition table decides "
            "who may make each move and when (409 with the reason if not now)."
        ),
        request=BookingTransitionSerializer,
        responses={200: BookingSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        booking = generics.get_object_or_404(bookings_for(request.user), pk=booking_id)
        actor = actor_for(request.user, booking)
        if actor is None:
            raise exceptions.NotFound("No such booking.")
        serializer = BookingTransitionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            transition(
                booking.pk,
                serializer.validated_data["status"],
                actor=actor,
                user=request.user,
                reason=serializer.validated_data.get("reason", ""),
                metadata=serializer.validated_data.get("metadata"),
                request=request,
            )
        except BookingRefused as exc:
            raise Refused(str(exc)) from exc
        booking = bookings_for(request.user).get(pk=booking.pk)
        return Response(BookingSerializer(booking, context={"request": request}).data)


class JobAuthFailed(exceptions.APIException):
    default_code = "scheduler_auth"


class JobView(APIView):
    """Cloud Scheduler calls this with an OIDC token (see scheduler.py), not a user's."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="jobs_run",
        summary="Run a scheduled job (Cloud Scheduler only)",
        description=(
            "Jobs: " + ", ".join(sorted(jobs.JOBS)) + ". Needs a Google-signed OIDC token for "
            "the scheduler service account. Idempotent; overlapping runs of one job are "
            "skipped."
        ),
        request=None,
        responses={
            200: JobResultSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=["jobs"],
    )
    def post(self, request: Request, job: str) -> Response:
        if job not in jobs.JOBS:
            raise exceptions.NotFound("No such job.")
        try:
            verify_request(request)
        except SchedulerAuthError as exc:
            error = JobAuthFailed(str(exc))
            error.status_code = exc.status
            raise error from exc
        try:
            run = jobs.run(job)
        except jobs.JobAlreadyRunning:
            return Response({"job": job, "run_id": None, "skipped": True, "result": {}})
        return Response({"job": job, "run_id": run.pk, "skipped": False, "result": run.result})
