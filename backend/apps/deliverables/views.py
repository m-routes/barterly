from django.db.models import Prefetch, Q
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking
from apps.common.permissions import IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.deliverables import services
from apps.deliverables.models import Deliverable, Status, Submission
from apps.deliverables.serializers import (
    DueDateSerializer,
    LibraryItemSerializer,
    ManualStatsSerializer,
    PostStatsSerializer,
    ReviewSerializer,
    SubmitSerializer,
    TrackedDeliverableSerializer,
)

TAG = ["deliverables"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


class DeliverableRefused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "deliverable_refused"


def refuse(exc):
    if exc.status == 400:
        return exceptions.ValidationError({"detail": exc.message})
    error = DeliverableRefused(exc.message)
    error.status_code = exc.status
    return error


def _with_details(rows):
    return rows.select_related(
        "booking__gig", "booking__agreement__current_version", "booking__talent__talent_profile"
    ).prefetch_related(
        Prefetch("submissions", queryset=Submission.objects.prefetch_related("files")),
        "stats__screenshot",
    )


def _one(deliverable_id) -> Deliverable:
    return _with_details(Deliverable.objects.filter(pk=deliverable_id)).get()


class BookingDeliverablesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="deliverables_for_booking",
        summary="A booking's deliverables",
        description=(
            "Barter and hybrid gigs: one per unit of each item in the agreement, with the "
            "latest submission, post stats (self-reported ones marked), and once approved "
            "the usage rights. Empty before check-in."
        ),
        responses={200: TrackedDeliverableSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, booking_id) -> Response:
        booking = (
            Booking.objects.select_related("gig", "agreement__current_version")
            .filter(Q(talent=request.user) | Q(vendor=request.user), pk=booking_id)
            .first()
        )
        if booking is None:
            raise exceptions.NotFound("No such booking.")
        services.for_booking(booking)
        rows = _with_details(Deliverable.objects.filter(booking=booking))
        return Response(TrackedDeliverableSerializer(rows, many=True).data)


class SubmitView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="deliverables_submit",
        summary="Hand in a deliverable",
        description=(
            "A post link and/or uploaded files (media ids). Public posts must carry the "
            "collaboration label: confirm it with `disclosure_confirmed`. Handing in the "
            "last one starts the host's 72-hour approval window."
        ),
        request=SubmitSerializer,
        responses={
            201: TrackedDeliverableSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, deliverable_id) -> Response:
        body = SubmitSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            services.submit(
                deliverable_id, talent=request.user, request=request, **body.validated_data
            )
        except Deliverable.DoesNotExist as exc:
            raise exceptions.NotFound("No such deliverable.") from exc
        except services.DeliverableError as exc:
            raise refuse(exc) from exc
        return Response(
            TrackedDeliverableSerializer(_one(deliverable_id)).data, status=status.HTTP_201_CREATED
        )


class ReviewView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="deliverables_review",
        summary="Approve a deliverable, or ask for changes",
        description=(
            "Asking for changes needs a note and is allowed twice per deliverable; after "
            "that, approve or open a dispute. Approving the last one releases a hybrid "
            "gig's stipend."
        ),
        request=ReviewSerializer,
        responses={
            200: TrackedDeliverableSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, deliverable_id) -> Response:
        body = ReviewSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            services.review(
                deliverable_id, vendor=request.user, request=request, **body.validated_data
            )
        except Deliverable.DoesNotExist as exc:
            raise exceptions.NotFound("No such deliverable.") from exc
        except services.DeliverableError as exc:
            raise refuse(exc) from exc
        return Response(TrackedDeliverableSerializer(_one(deliverable_id)).data)


class DueDateView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="deliverables_due_date",
        summary="Move a deliverable's due date",
        description="During the stay or up to 30 days after it. The talent is told.",
        request=DueDateSerializer,
        responses={
            200: TrackedDeliverableSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def patch(self, request: Request, deliverable_id) -> Response:
        body = DueDateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            services.set_due_date(
                deliverable_id,
                vendor=request.user,
                request=request,
                due_date=body.validated_data["due_date"],
            )
        except Deliverable.DoesNotExist as exc:
            raise exceptions.NotFound("No such deliverable.") from exc
        except services.DeliverableError as exc:
            raise refuse(exc) from exc
        return Response(TrackedDeliverableSerializer(_one(deliverable_id)).data)


class ManualStatsView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="deliverables_report_stats",
        summary="Enter a post's numbers by hand",
        description=(
            "With a screenshot of the numbers (an uploaded photo). Shown to the host as "
            "self-reported, beside any numbers from the platform."
        ),
        request=ManualStatsSerializer,
        responses={201: PostStatsSerializer, 400: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, deliverable_id) -> Response:
        body = ManualStatsSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            stats = services.report_stats(
                deliverable_id, talent=request.user, request=request, **body.validated_data
            )
        except Deliverable.DoesNotExist as exc:
            raise exceptions.NotFound("No such deliverable.") from exc
        except services.DeliverableError as exc:
            raise refuse(exc) from exc
        return Response(PostStatsSerializer(stats).data, status=status.HTTP_201_CREATED)


class ToReviewView(generics.ListAPIView):
    permission_classes = [IsVendor]
    serializer_class = TrackedDeliverableSerializer

    def get_queryset(self):
        rows = Deliverable.objects.filter(
            booking__vendor=self.request.user, status=Status.SUBMITTED
        ).order_by("submitted_at")
        return _with_details(rows)

    @extend_schema(
        operation_id="deliverables_to_review",
        summary="Deliverables waiting for your review",
        description="Oldest submission first, across your bookings.",
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class LibraryView(generics.ListAPIView):
    permission_classes = [IsVendor]
    serializer_class = LibraryItemSerializer

    def get_queryset(self):
        rows = Deliverable.objects.filter(
            booking__vendor=self.request.user, status=Status.APPROVED
        ).order_by("-approved_at")
        return _with_details(rows)

    @extend_schema(
        operation_id="deliverables_library",
        summary="Your approved content",
        description=(
            "Newest first, each with its usage rights from the agreement (and until when "
            "they last), the post link and download links (valid 10 minutes)."
        ),
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)
