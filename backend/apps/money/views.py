from django.conf import settings
from django.db.models import Q
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking
from apps.common.permissions import IsAdminRole, IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.money import deliverables, escrow, webhooks
from apps.money.gateway.base import GatewayError
from apps.money.models import DeliverableSubmission, Escrow, EscrowControl, ReconciliationRun
from apps.money.serializers import (
    DeliverableSubmissionSerializer,
    EscrowCheckoutSerializer,
    EscrowDecisionSerializer,
    EscrowOverviewSerializer,
    EscrowSerializer,
    KillSwitchSerializer,
    ReconciliationRunSerializer,
    ReviewDeliverableSerializer,
    ReviewResultSerializer,
    SubmitDeliverableSerializer,
)

TAG = ["money"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}


class MoneyRefused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "money_refused"


def refuse(exc):
    if exc.status == 400:
        return exceptions.ValidationError({"detail": exc.message})
    error = MoneyRefused(exc.message)
    error.status_code = exc.status
    return error


def _booking_for(user, booking_id) -> Booking:
    booking = (
        Booking.objects.select_related("gig")
        .filter(Q(talent=user) | Q(vendor=user), pk=booking_id)
        .first()
    )
    if booking is None:
        raise exceptions.NotFound("No such booking.")
    return booking


def _has_perm(perm: str):
    class HasPerm(BasePermission):
        message = "You don't have permission to do that."

        def has_permission(self, request, view) -> bool:
            return bool(request.user and request.user.has_perm(perm))

    return HasPerm


class EscrowView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="money_escrow",
        summary="A booking's escrow",
        description=(
            "For paid and hybrid gigs: the stipend held for the booking, and what funding "
            "it costs now (stipend + the gateway's fee + GST on the fee). The host funds it "
            "before check-in. Amounts are whole paise."
        ),
        responses={200: EscrowOverviewSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, booking_id) -> Response:
        booking = _booking_for(request.user, booking_id)
        needed = escrow.needs_escrow(booking)
        record = Escrow.objects.filter(booking=booking).first()
        quote = None
        if needed and (record is None or record.status in ("awaiting_funding", "funding")):
            try:
                amounts = escrow.quote(booking)
                quote = {f"{k}_paise": v for k, v in amounts.items()}
            except escrow.EscrowError:
                quote = None
        data = {"needs_escrow": needed, "paused": escrow.paused(), "escrow": record, "quote": quote}
        return Response(EscrowOverviewSerializer(data).data)


class FundView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="money_escrow_fund",
        summary="Start funding a booking's stipend",
        description=(
            "Creates the gateway order for the host to pay at checkout (asking again before "
            "paying returns the same order). The money is held once the gateway confirms "
            "the payment. 503 while the kill switch is on."
        ),
        request=None,
        responses={
            200: EscrowCheckoutSerializer,
            409: ErrorSerializer,
            503: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        try:
            record, order_id = escrow.start_funding(
                booking_id, vendor=request.user, request=request
            )
        except Booking.DoesNotExist as exc:
            raise exceptions.NotFound("No such booking.") from exc
        except escrow.EscrowError as exc:
            raise refuse(exc) from exc
        data = {
            "escrow": record,
            "order_id": order_id,
            "amount_paise": record.total_paise,
            "currency": "INR",
            "key_id": settings.RAZORPAY_KEY_ID,
        }
        return Response(EscrowCheckoutSerializer(data).data)


class DeliverablesView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsTalent()]
        return super().get_permissions()

    @extend_schema(
        operation_id="money_deliverables",
        summary="Work handed in for a booking",
        description="Newest first. Both sides of the booking can see them.",
        responses={200: DeliverableSubmissionSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, booking_id) -> Response:
        booking = _booking_for(request.user, booking_id)
        return Response(DeliverableSubmissionSerializer(booking.submissions.all(), many=True).data)

    @extend_schema(
        operation_id="money_deliverables_submit",
        summary="Hand in work",
        description=(
            "A note and/or links. The host approves (releasing the stipend) or asks for "
            "changes; with no answer for 72 hours after the latest submission the stipend "
            "is released automatically."
        ),
        request=SubmitDeliverableSerializer,
        responses={
            201: DeliverableSubmissionSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        body = SubmitDeliverableSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            submission = deliverables.submit(
                booking_id, talent=request.user, request=request, **body.validated_data
            )
        except Booking.DoesNotExist as exc:
            raise exceptions.NotFound("No such booking.") from exc
        except deliverables.DeliverableError as exc:
            raise refuse(exc) from exc
        return Response(
            DeliverableSubmissionSerializer(submission).data, status=status.HTTP_201_CREATED
        )


class ReviewDeliverableView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="money_deliverables_review",
        summary="Approve work, or ask for changes",
        description=(
            "Approving releases the stipend: commission and GST to Barterly, TDS withheld, "
            "the rest paid out to the talent. Asking for changes needs a note."
        ),
        request=ReviewDeliverableSerializer,
        responses={
            200: ReviewResultSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, submission_id) -> Response:
        body = ReviewDeliverableSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            submission, record, held_back = deliverables.review(
                submission_id, vendor=request.user, request=request, **body.validated_data
            )
        except DeliverableSubmission.DoesNotExist as exc:
            raise exceptions.NotFound("No such submission.") from exc
        except deliverables.DeliverableError as exc:
            raise refuse(exc) from exc
        data = {"submission": submission, "escrow": record, "release_held_back": held_back}
        return Response(ReviewResultSerializer(data).data)


class DecideView(APIView):
    permission_classes = [IsAdminRole, _has_perm("money.decide_escrow")]

    @extend_schema(
        operation_id="money_admin_decide",
        summary="Decide a held escrow (admin)",
        description=(
            "Release it all to the talent, refund it all to the host, or split it "
            "(talent_paise to the talent, the rest refunded). Works on a disputed (frozen) "
            "escrow. Audited, with the note."
        ),
        request=EscrowDecisionSerializer,
        responses={
            200: EscrowSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            503: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        body = EscrowDecisionSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            record = escrow.decide(booking_id, admin=request.user, **body.validated_data)
        except Booking.DoesNotExist as exc:
            raise exceptions.NotFound("No such booking.") from exc
        except escrow.EscrowError as exc:
            raise refuse(exc) from exc
        return Response(EscrowSerializer(record).data)


class KillSwitchView(APIView):
    permission_classes = [IsAdminRole, _has_perm("money.view_escrowcontrol")]

    def get_permissions(self):
        if self.request.method == "PUT":
            return [IsAdminRole(), _has_perm("money.toggle_kill_switch")()]
        return super().get_permissions()

    @extend_schema(
        operation_id="money_admin_kill_switch",
        summary="The escrow kill switch (admin)",
        description="Paused here or by the ESCROW_PAUSED setting: no funding or payouts.",
        responses={200: KillSwitchSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        control, _ = EscrowControl.objects.get_or_create(pk=1)
        return Response(KillSwitchSerializer(control).data)

    @extend_schema(
        operation_id="money_admin_kill_switch_set",
        summary="Pause or resume escrow funding and payouts (admin)",
        request=KillSwitchSerializer,
        responses={200: KillSwitchSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def put(self, request: Request) -> Response:
        body = KillSwitchSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        paused = body.validated_data["paused"]
        reason = body.validated_data.get("reason", "")
        if paused and not reason.strip():
            raise exceptions.ValidationError({"reason": "Say why you're pausing."})
        control = escrow.set_paused(paused, by=request.user, reason=reason)
        return Response(KillSwitchSerializer(control).data)


class ReconciliationView(APIView):
    permission_classes = [IsAdminRole, _has_perm("money.view_reconciliationrun")]

    @extend_schema(
        operation_id="money_admin_reconciliation",
        summary="Recent daily reconciliations (admin)",
        description="The last 30 days: ledger totals against the gateway's, in paise.",
        responses={200: ReconciliationRunSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        runs = ReconciliationRun.objects.all()[:30]
        return Response(ReconciliationRunSerializer(runs, many=True).data)


class WebhookRejected(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_webhook"


class WebhookView(APIView):
    """The gateway calls this; the signature, not a user, is the credential."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="money_razorpay_webhook",
        summary="Razorpay escrow events (webhook)",
        description=(
            "payment.captured/failed, refund.processed/failed, transfer.processed/settled/"
            "failed. Signed with X-Razorpay-Signature (HMAC-SHA256 of the body) and "
            "identified by X-Razorpay-Event-Id: each event is applied once; repeats answer "
            "200 and change nothing."
        ),
        request={"application/json": {"type": "object", "additionalProperties": True}},
        responses={
            200: {"type": "object", "properties": {"outcome": {"type": "string"}}},
            400: ErrorSerializer,
        },
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        try:
            outcome = webhooks.handle(request.body, request.headers)
        except GatewayError as exc:
            raise WebhookRejected(str(exc)) from exc
        return Response({"outcome": outcome})
