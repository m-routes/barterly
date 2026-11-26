import logging

from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications.models import Application
from apps.bookings import cancellation, confirmation, jobs
from apps.bookings.lifecycle import BEFORE_CHECK_IN, Actor, BookingStatus
from apps.bookings.models import REASONS_FOR, Booking, CancellationEffect, CancellationReason
from apps.bookings.scheduler import SchedulerAuthError, verify_request, verify_task_request
from apps.bookings.serializers import (
    BookingListItemSerializer,
    BookingSerializer,
    BookingTransitionSerializer,
    CancelPreviewSerializer,
    CancelSerializer,
    JobResultSerializer,
    UnlockedSerializer,
)
from apps.bookings.services import BookingRefused, accept_offer, actor_for, transition
from apps.common.permissions import IsTalent, staff_can
from apps.common.serializers import ErrorSerializer

logger = logging.getLogger(__name__)
TAG = ["bookings"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


class Refused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "That can't happen from the booking's current status."
    default_code = "transition_refused"


def bookings_for(user):
    qs = Booking.objects.select_related("gig", "cancellation").prefetch_related("events")
    if staff_can(user, "bookings.view_booking"):
        return qs
    return qs.filter(Q(talent=user) | Q(vendor=user))


class AcceptOfferView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="applications_accept",
        summary="Accept an offer",
        description=(
            "The application becomes confirmed and a booking is created awaiting "
            "signatures; it takes a slot once both sides sign the agreement. Refused (409) "
            "when the offer has expired, the gig has no slot left, or you already have a "
            "booking for those dates."
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
        qs = bookings_for(self.request.user).order_by("-created_at")
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
            "Check in, start delivering, complete, report a no-show, dispute, review; "
            "admins also resolve disputes and refund. Cancelling before check-in goes "
            "through bookings/{id}/cancel/ (a reason from the list). The transition table "
            "decides who may make each move and when (409 with the reason if not now)."
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
        to = serializer.validated_data["status"]
        if to == BookingStatus.CANCELLED and booking.status in BEFORE_CHECK_IN:
            if actor != Actor.ADMIN:
                raise exceptions.ValidationError(
                    {"status": "Cancel with a reason from the list: POST .../cancel/."}
                )
            try:
                cancellation.cancel(
                    booking.pk,
                    user=request.user,
                    by=Actor.ADMIN,
                    reason=CancellationReason.ADMIN,
                    note=serializer.validated_data.get("reason", ""),
                    request=request,
                )
            except cancellation.CancellationRefused as exc:
                raise Refused(exc.message) from exc
            booking = bookings_for(request.user).get(pk=booking.pk)
            return Response(BookingSerializer(booking, context={"request": request}).data)
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


def _party_booking(request, booking_id):
    booking = generics.get_object_or_404(
        bookings_for(request.user).select_related(
            "gig__property", "talent", "vendor", "agreement__current_version"
        ),
        pk=booking_id,
    )
    party = actor_for(request.user, booking)
    if party not in (Actor.TALENT, Actor.VENDOR):
        raise exceptions.NotFound("No such booking.")
    return booking, party


class CancelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="bookings_cancel_preview",
        summary="What cancelling now would do",
        description=(
            "The reasons you can pick, and the effect on your reliability score under the "
            "agreement's cancellation policy if you cancel now."
        ),
        responses={200: CancelPreviewSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, booking_id) -> Response:
        booking, party = _party_booking(request, booking_id)
        effect = cancellation.preview(booking, by=party)
        return Response(
            CancelPreviewSerializer(
                {
                    "reasons": [
                        {"code": code, "label": CancellationReason(code).label}
                        for code in REASONS_FOR[party]
                    ],
                    "effect": effect.effect,
                    "effect_label": CancellationEffect(effect.effect).label,
                    "policy": effect.policy,
                    "notice_days": effect.notice_days,
                    "days_before_start": effect.days_before_start,
                }
            ).data
        )

    @extend_schema(
        operation_id="bookings_cancel",
        summary="Cancel before check-in",
        description=(
            "Either side, while the booking is awaiting signatures or confirmed. Pick a "
            "reason (say more for other). A confirmed booking's place is freed and offered "
            "on: held offers open again, or the next shortlisted applicant is offered it."
        ),
        request=CancelSerializer,
        responses={200: BookingSerializer, 400: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        booking, party = _party_booking(request, booking_id)
        serializer = CancelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            cancellation.cancel(
                booking.pk,
                user=request.user,
                by=party,
                reason=serializer.validated_data["reason"],
                note=serializer.validated_data.get("note", ""),
                request=request,
            )
        except cancellation.CancellationRefused as exc:
            if exc.status == 400:
                raise exceptions.ValidationError({"reason": exc.message}) from exc
            raise Refused(exc.message) from exc
        booking = bookings_for(request.user).get(pk=booking.pk)
        return Response(BookingSerializer(booking, context={"request": request}).data)


class LockedUntilConfirmed(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "These details are shared once both sides have signed."
    default_code = "not_confirmed"


class UnlockedView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="bookings_details",
        summary="Contact details and the exact address",
        description=(
            "Once both sides have signed (until the stay ends or is cancelled): each side's "
            "verified phone, and for the talent the exact address, directions and a maps "
            "link. 409 before then."
        ),
        responses={200: UnlockedSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, booking_id) -> Response:
        booking, party = _party_booking(request, booking_id)
        details = confirmation.unlocked_details(booking, party=party)
        if details is None:
            raise LockedUntilConfirmed()
        data = {
            "booking_id": details.booking_id,
            "status": details.status,
            "host": details.host.__dict__,
            "talent": details.talent.__dict__,
            "place": (
                {**details.place.__dict__, "maps_url": details.place.maps_url}
                if details.place
                else None
            ),
        }
        return Response(UnlockedSerializer(data).data)


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


class TaskFailed(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "The task failed; Cloud Tasks will retry it."
    default_code = "task_retry"


class TaskView(APIView):
    """Cloud Tasks calls this with an OIDC token for the tasks service account. A task
    that raises answers 503, so Cloud Tasks retries it with the queue's backoff."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="tasks_run",
        summary="Run a queued task (Cloud Tasks only)",
        description=(
            "Needs a Google-signed OIDC token for the tasks service account. The body is the "
            "task's payload. 503 asks Cloud Tasks to retry."
        ),
        request={"application/json": {"type": "object", "additionalProperties": True}},
        responses={
            204: None,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=["jobs"],
    )
    def post(self, request: Request, name: str) -> Response:
        from apps.media.tasks import run_task

        try:
            verify_task_request(request)
        except SchedulerAuthError as exc:
            error = JobAuthFailed(str(exc))
            error.status_code = exc.status
            raise error from exc
        payload = request.data if isinstance(request.data, dict) else {}
        try:
            run_task(name, payload)
        except LookupError as exc:
            raise exceptions.NotFound("No such task.") from exc
        except Exception as exc:
            logger.warning("Task will be retried", extra={"task": name, "error": str(exc)})
            raise TaskFailed() from exc
        return Response(status=status.HTTP_204_NO_CONTENT)
