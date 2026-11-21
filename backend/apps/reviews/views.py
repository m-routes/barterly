from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking
from apps.common.permissions import IsAdminRole
from apps.common.serializers import ErrorSerializer
from apps.reviews import reputation, services
from apps.reviews.models import Review, ReviewReport, ReviewStatus, Side
from apps.reviews.serializers import (
    BookingReviewsSerializer,
    ModerationSerializer,
    QueueItemSerializer,
    ReplyRequestSerializer,
    ReplySerializer,
    ReportRequestSerializer,
    StayReviewSerializer,
    UserReputationSerializer,
    WriteReviewSerializer,
)

TAG = ["reviews"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}
S = ReviewStatus


class ReviewRefused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "review_refused"


def refuse(exc):
    if exc.status == 400:
        return exceptions.ValidationError({"detail": exc.message})
    error = ReviewRefused(exc.message)
    error.status_code = exc.status
    return error


class CanModerate(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.has_perm("reviews.moderate_review"))


def _with_people(rows):
    return rows.select_related(
        "author__talent_profile", "author__vendor_profile", "reply"
    ).prefetch_related("reports")


class BookingReviewsView(APIView):
    permission_classes = [IsAuthenticated]

    def _booking(self, request, booking_id) -> tuple[Booking, str]:
        booking = (
            Booking.objects.select_related("gig")
            .filter(Q(talent=request.user) | Q(vendor=request.user), pk=booking_id)
            .first()
        )
        if booking is None:
            raise exceptions.NotFound("No such booking.")
        return booking, services.side_of(booking, request.user)

    @extend_schema(
        operation_id="reviews_for_booking",
        summary="This stay's reviews, as you see them",
        description=(
            "Double-blind: the other side's review appears only once both are in (or the "
            "14-day window has closed) and it's published."
        ),
        responses={200: BookingReviewsSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, booking_id) -> Response:
        booking, side = self._booking(request, booking_id)
        reviews = list(_with_people(booking.reviews.all()))
        mine = next((r for r in reviews if r.author_id == request.user.pk), None)
        theirs = next((r for r in reviews if r.author_id != request.user.pk), None)
        reviewable = booking.status in services.REVIEWABLE
        closes = services.window_closes(booking) if reviewable else None
        data = {
            "reviewing": side,
            "can_review": bool(reviewable and mine is None and timezone.now() < closes),
            "window_closes_at": closes,
            "category_labels": services.CATEGORY_LABELS[side],
            "mine": mine,
            "theirs": theirs if theirs and theirs.status == S.PUBLISHED else None,
            "they_have_reviewed": theirs is not None,
        }
        return Response(BookingReviewsSerializer(data).data)

    @extend_schema(
        operation_id="reviews_submit",
        summary="Review the other side of a completed stay",
        description=(
            "Once per side, within 14 days of completion. It stays hidden until the other "
            "side reviews too (or the window closes). It can't be edited after."
        ),
        request=WriteReviewSerializer,
        responses={201: StayReviewSerializer, 400: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        body = WriteReviewSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            review = services.submit(
                booking_id, author=request.user, request=request, **body.validated_data
            )
        except Booking.DoesNotExist as exc:
            raise exceptions.NotFound("No such booking.") from exc
        except services.ReviewError as exc:
            raise refuse(exc) from exc
        review = _with_people(Review.objects.filter(pk=review.pk)).get()
        return Response(StayReviewSerializer(review).data, status=status.HTTP_201_CREATED)


class UserReviewsView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = StayReviewSerializer

    def get_queryset(self):
        side = self.request.query_params.get("side", Side.TALENT)
        if side not in Side.values:
            raise exceptions.ValidationError({"side": "talent or host"})
        rows = Review.objects.filter(
            subject_id=self.kwargs["user_id"], subject_side=side, status=S.PUBLISHED
        ).order_by("-published_at")
        return _with_people(rows)

    @extend_schema(
        operation_id="reviews_of_user",
        summary="Published reviews of someone",
        description="Newest first, with their reply if they gave one.",
        parameters=[OpenApiParameter("side", str, enum=Side.values)],
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class ReputationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="reviews_reputation",
        summary="Someone's reputation",
        description="As talent and as a host: rating, completion rate, response time, badges.",
        responses={200: UserReputationSerializer, 401: ErrorSerializer},
        tags=TAG,
    )
    def get(self, request: Request, user_id) -> Response:
        data = {
            "talent": reputation.for_user(user_id, Side.TALENT),
            "host": reputation.for_user(user_id, Side.HOST),
        }
        return Response(UserReputationSerializer(data).data)


class ReplyView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="reviews_reply",
        summary="Answer a review of you (once)",
        request=ReplyRequestSerializer,
        responses={201: ReplySerializer, 400: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, review_id) -> Response:
        body = ReplyRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            answer = services.reply(
                review_id, user=request.user, request=request, text=body.validated_data["text"]
            )
        except Review.DoesNotExist as exc:
            raise exceptions.NotFound("No such review of you.") from exc
        except services.ReviewError as exc:
            raise refuse(exc) from exc
        return Response(ReplySerializer(answer).data, status=status.HTTP_201_CREATED)


class ReportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="reviews_report",
        summary="Report a review",
        description="A moderator looks at it. One report per person per review.",
        request=ReportRequestSerializer,
        responses={201: None, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, review_id) -> Response:
        body = ReportRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            services.report(review_id, user=request.user, request=request, **body.validated_data)
        except Review.DoesNotExist as exc:
            raise exceptions.NotFound("No such review.") from exc
        except services.ReviewError as exc:
            raise refuse(exc) from exc
        return Response(status=status.HTTP_201_CREATED)


class QueueView(generics.ListAPIView):
    permission_classes = [IsAdminRole, CanModerate]
    serializer_class = QueueItemSerializer

    def get_queryset(self):
        open_reports = ReviewReport.objects.filter(review=OuterRef("pk"), resolved_at__isnull=True)
        rows = Review.objects.filter(Q(status=S.HELD) | Q(Exists(open_reports))).order_by(
            "submitted_at"
        )
        return _with_people(rows)

    @extend_schema(
        operation_id="reviews_admin_queue",
        summary="Reviews waiting for moderation (admin)",
        description="Held for flagged words or contact details, or reported. Oldest first.",
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class ModerateView(APIView):
    permission_classes = [IsAdminRole, CanModerate]

    @extend_schema(
        operation_id="reviews_admin_moderate",
        summary="Allow or remove a review (admin)",
        description="Removing hides it and stops it counting. Audited, with the note.",
        request=ModerationSerializer,
        responses={200: StayReviewSerializer, 400: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, review_id) -> Response:
        body = ModerationSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            review = services.moderate(
                review_id, admin=request.user, request=request, **body.validated_data
            )
        except Review.DoesNotExist as exc:
            raise exceptions.NotFound("No such review.") from exc
        except services.ReviewError as exc:
            raise refuse(exc) from exc
        return Response(StayReviewSerializer(review).data)
