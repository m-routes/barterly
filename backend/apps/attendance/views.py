from datetime import date

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.attendance import hours, services, signing
from apps.attendance.models import CheckIn, HourLog, HourStatus
from apps.attendance.serializers import (
    ArrivalsSerializer,
    CheckInRequestSerializer,
    CheckInSerializer,
    FlagReviewSerializer,
    HourLogSerializer,
    HourReviewSerializer,
    HoursCheckSerializer,
    HoursWeekSerializer,
    LoggedHoursSerializer,
    LogHoursSerializer,
    NoShowSerializer,
    PassRequestSerializer,
    PassSerializer,
    PendingHourLogSerializer,
    PublicKeySerializer,
    SyncRequestSerializer,
    SyncResponseSerializer,
    _name,
)
from apps.bookings.models import Booking
from apps.common.permissions import IsAdminRole, IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.privacy.models import Purpose
from apps.privacy.services import consents

TAG = ["attendance"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


class AttendanceRefused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "attendance_refused"


def refuse(exc):
    if exc.status == 400:
        return exceptions.ValidationError({"detail": exc.message})
    if exc.status == 404:
        return exceptions.NotFound(exc.message)
    error = AttendanceRefused(exc.message)
    error.status_code = exc.status
    return error


class CanReviewCheckIns(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.has_perm("attendance.review_checkin"))


def _booking_for(user, booking_id) -> Booking:
    booking = (
        Booking.objects.select_related("gig", "agreement__current_version")
        .filter(Q(talent=user) | Q(vendor=user), pk=booking_id)
        .first()
    )
    if booking is None:
        raise exceptions.NotFound("No such booking.")
    return booking


# ---------- Talent ----------


class PassView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="attendance_pass",
        summary="Your check-in pass",
        description=(
            "A signed token to show as a QR code, and the secret for the six-digit "
            "fallback code. Valid offline until `valid_until`; ask again for a fresh one. "
            "Send your location to record your distance from the property at check-in "
            "(it never blocks check-in). The location is kept only if you have given "
            "location consent (POST /api/v1/privacy/consents/); otherwise it is ignored."
        ),
        request=PassRequestSerializer,
        responses={200: PassSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        body = PassRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        location = body.validated_data["location"]
        if location and not consents.has_consent(request.user, Purpose.LOCATION):
            location = None  # no consent: we don't keep where they are
        try:
            attendance_pass = services.talent_pass(
                booking_id, talent=request.user, location=location
            )
        except Booking.DoesNotExist as exc:
            raise exceptions.NotFound("No such booking.") from exc
        except services.AttendanceError as exc:
            raise refuse(exc) from exc
        return Response(
            PassSerializer(
                {
                    "booking_id": attendance_pass.booking_id,
                    "token": services.token_for(attendance_pass),
                    "code_secret": attendance_pass.code_secret,
                    "valid_from": attendance_pass.valid_from,
                    "valid_until": attendance_pass.valid_until,
                }
            ).data
        )


class AttendanceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="attendance_check_in_record",
        summary="A booking's check-in record",
        description="404 until the talent is checked in.",
        responses={200: CheckInSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, booking_id) -> Response:
        booking = _booking_for(request.user, booking_id)
        record = CheckIn.objects.filter(booking=booking).first()
        if record is None:
            raise exceptions.NotFound("Not checked in yet.")
        return Response(CheckInSerializer(record).data)


class HoursView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTalent()]
        return super().get_permissions()

    @extend_schema(
        operation_id="attendance_hours_week",
        summary="Hours logged in one week of a stay",
        description="Monday to Sunday containing `week` (default: this week), with the limits.",
        parameters=[OpenApiParameter("week", date, required=False)],
        responses={200: HoursWeekSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, booking_id) -> Response:
        booking = _booking_for(request.user, booking_id)
        try:
            week = date.fromisoformat(request.query_params.get("week") or "")
        except ValueError:
            week = timezone.localdate()
        return Response(HoursWeekSerializer(hours.week_summary(booking, week)).data)

    @extend_schema(
        operation_id="attendance_hours_log",
        summary="Log a day's hours",
        description=(
            "One log per day (logging again replaces it until the host confirms). Refused "
            "if it breaks the weekly cap or leaves no day off; `check.warnings` says when "
            "you're close."
        ),
        request=LogHoursSerializer,
        responses={
            201: LoggedHoursSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        body = LogHoursSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            entry, result = hours.log(
                booking_id, talent=request.user, request=request, **body.validated_data
            )
        except Booking.DoesNotExist as exc:
            raise exceptions.NotFound("No such booking.") from exc
        except hours.HoursError as exc:
            raise refuse(exc) from exc
        return Response(
            LoggedHoursSerializer({"log": entry, "check": result}).data,
            status=status.HTTP_201_CREATED,
        )


class HoursCheckView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="attendance_hours_check",
        summary="Check hours before logging them",
        description="Whether a log would be allowed, why not, and any warnings. Saves nothing.",
        request=LogHoursSerializer,
        responses={200: HoursCheckSerializer, 400: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        body = LogHoursSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            result = hours.preview(
                booking_id,
                talent=request.user,
                day=body.validated_data["day"],
                minutes=body.validated_data["minutes"],
            )
        except Booking.DoesNotExist as exc:
            raise exceptions.NotFound("No such booking.") from exc
        except hours.HoursError as exc:
            raise refuse(exc) from exc
        return Response(HoursCheckSerializer(result).data)


# ---------- Host ----------


class KeysView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="attendance_keys",
        summary="Public keys that sign check-in passes",
        description="Cache these to verify QR passes offline (Ed25519).",
        responses={200: PublicKeySerializer(many=True), 401: ErrorSerializer},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(PublicKeySerializer(signing.public_keys(), many=True).data)


class ArrivalsView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="attendance_arrivals",
        summary="The day's expected arrivals, for offline check-in",
        description=(
            "Confirmed bookings in their check-in window on `date` (default today), each "
            "with what's needed to check its QR or code offline, and everyone in house "
            "(for check-out and hours). Cache it with the public keys."
        ),
        parameters=[OpenApiParameter("date", date, required=False)],
        responses={200: ArrivalsSerializer, 403: ErrorSerializer, 401: ErrorSerializer},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        now = timezone.now()
        try:
            day = date.fromisoformat(request.query_params.get("date") or "")
        except ValueError:
            day = timezone.localdate(now)
        expected, in_house = services.arrivals(request.user, day, now=now)
        pending = dict(
            HourLog.objects.filter(booking__in=in_house, status=HourStatus.PENDING)
            .values_list("booking_id")
            .annotate(n=Count("id"))
        )
        data = {
            "date": day,
            "generated_at": now,
            "public_keys": signing.public_keys(),
            "code_period_seconds": signing.CODE_STEP_SECONDS,
            "clock_skew_seconds": settings.ATTENDANCE_CLOCK_SKEW_SECONDS,
            "arrivals": [
                {
                    "booking_id": a.booking.pk,
                    "talent_id": a.booking.talent_id,
                    "talent_name": _name(a.booking.talent),
                    "gig_title": a.booking.gig.title,
                    "property_name": getattr(a.booking.gig.property, "name", "") or "",
                    "start_date": a.booking.start_date,
                    "end_date": a.booking.end_date,
                    "status": a.booking.status,
                    "problem": a.problem,
                    "pass_id": a.attendance_pass.pk,
                    "code_secret": a.attendance_pass.code_secret,
                    "pass_valid_from": a.attendance_pass.valid_from,
                    "pass_valid_until": a.attendance_pass.valid_until,
                    "no_show_from": services.no_show_from(a.booking),
                }
                for a in expected
            ],
            "in_house": [
                {
                    "booking_id": b.pk,
                    "talent_name": _name(b.talent),
                    "gig_title": b.gig.title,
                    "start_date": b.start_date,
                    "end_date": b.end_date,
                    "status": b.status,
                    "hours_to_review": pending.get(b.pk, 0),
                }
                for b in in_house
            ],
        }
        return Response(ArrivalsSerializer(data).data)


class CheckInView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="attendance_check_in",
        summary="Check a talent in",
        description=(
            "By the QR pass (`token`), the six-digit `code`, or by hand (`reason`). "
            "`scanned_at` is when it happened, for a check-in queued offline (up to 72 "
            "hours). Repeating a `client_id` returns the first result. The talent's "
            "distance from the property is recorded and flagged if large, never blocking."
        ),
        request=CheckInRequestSerializer,
        responses={
            201: CheckInSerializer,
            200: CheckInSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        body = CheckInRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            outcome = services.check_in(vendor=request.user, request=request, **body.validated_data)
        except services.AttendanceError as exc:
            raise refuse(exc) from exc
        code = status.HTTP_201_CREATED if outcome.status == "applied" else status.HTTP_200_OK
        return Response(CheckInSerializer(outcome.check_in).data, status=code)


class SyncView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="attendance_sync",
        summary="Sync check-ins queued offline",
        description=(
            "Each is applied on its own, in order: `applied`, `duplicate` (already done) "
            "or `refused` with the reason. Safe to send again."
        ),
        request=SyncRequestSerializer,
        responses={200: SyncResponseSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        body = SyncRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        results = services.sync(request.user, body.validated_data["events"], request=request)
        return Response(SyncResponseSerializer({"results": results}).data)


class CheckOutView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="attendance_check_out",
        summary="Check a talent out (ends the stay)",
        request=None,
        responses={200: CheckInSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        try:
            record = services.check_out(booking_id, vendor=request.user, request=request)
        except services.AttendanceError as exc:
            raise refuse(exc) from exc
        return Response(CheckInSerializer(record).data)


class NoShowView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="attendance_no_show",
        summary="Mark a no-show",
        description=(
            "From the grace period into the first day (`no_show_from` in arrivals). It "
            "counts against the talent's reliability score; they can dispute it."
        ),
        request=NoShowSerializer,
        responses={
            200: {"type": "object", "properties": {"status": {"type": "string"}}},
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        body = NoShowSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            booking = services.no_show(
                booking_id,
                vendor=request.user,
                request=request,
                reason=body.validated_data["reason"],
            )
        except services.AttendanceError as exc:
            raise refuse(exc) from exc
        return Response({"status": booking.status})


class PendingHoursView(generics.ListAPIView):
    permission_classes = [IsVendor]
    serializer_class = PendingHourLogSerializer

    def get_queryset(self):
        return (
            HourLog.objects.filter(booking__vendor=self.request.user, status=HourStatus.PENDING)
            .select_related("booking__gig", "booking__talent__talent_profile")
            .order_by("day")
        )

    @extend_schema(
        operation_id="attendance_hours_pending",
        summary="Hours waiting for you to confirm",
        description="Oldest day first.",
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class HourReviewView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="attendance_hours_review",
        summary="Confirm or dispute a day's hours",
        description="Disputing needs a note; the talent is told.",
        request=HourReviewSerializer,
        responses={200: HourLogSerializer, 400: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, log_id) -> Response:
        body = HourReviewSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            entry = hours.review(
                log_id, vendor=request.user, request=request, **body.validated_data
            )
        except HourLog.DoesNotExist as exc:
            raise exceptions.NotFound("No such hours.") from exc
        except hours.HoursError as exc:
            raise refuse(exc) from exc
        return Response(HourLogSerializer(entry).data)


# ---------- Admin ----------


class FlaggedView(generics.ListAPIView):
    permission_classes = [IsAdminRole, CanReviewCheckIns]
    serializer_class = CheckInSerializer

    def get_queryset(self):
        return (
            CheckIn.objects.exclude(flag="")
            .filter(reviewed_at__isnull=True)
            .order_by("checked_in_at")
        )

    @extend_schema(
        operation_id="attendance_admin_flagged",
        summary="Check-ins flagged for review (admin)",
        description="Far from the property, not yet reviewed. Oldest first.",
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class FlagReviewView(APIView):
    permission_classes = [IsAdminRole, CanReviewCheckIns]

    @extend_schema(
        operation_id="attendance_admin_flag_review",
        summary="Mark a flagged check-in reviewed (admin)",
        request=FlagReviewSerializer,
        responses={200: CheckInSerializer, 400: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, check_in_id) -> Response:
        body = FlagReviewSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            record = services.review_flag(
                check_in_id, admin=request.user, note=body.validated_data["note"]
            )
        except CheckIn.DoesNotExist as exc:
            raise exceptions.NotFound("No such check-in.") from exc
        except services.AttendanceError as exc:
            raise refuse(exc) from exc
        return Response(CheckInSerializer(record).data)
