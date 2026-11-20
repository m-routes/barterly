from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import AllowAny, BasePermission, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking
from apps.common.permissions import IsAdminRole, IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.common.services.audit import log_action
from apps.money import deliverables, escrow, payout_accounts, payouts, wallet, webhooks
from apps.money.gateway.base import GatewayError
from apps.money.models import (
    DeliverableSubmission,
    Escrow,
    EscrowControl,
    Payout,
    PayoutAccount,
    PayoutAttemptStatus,
    PayoutRun,
    PayoutTrigger,
    ReconciliationRun,
)
from apps.money.serializers import (
    DeliverableSubmissionSerializer,
    EscrowCheckoutSerializer,
    EscrowDecisionSerializer,
    EscrowOverviewSerializer,
    EscrowSerializer,
    KillSwitchSerializer,
    LinkPayoutAccountSerializer,
    PayoutAccountSerializer,
    PayoutRetrySerializer,
    PayoutRunDetailSerializer,
    PayoutRunSerializer,
    PayoutSerializer,
    ReconciliationRunSerializer,
    ReviewDeliverableSerializer,
    ReviewResultSerializer,
    StatementSerializer,
    SubmitDeliverableSerializer,
    TdsRecordSerializer,
    WalletEntrySerializer,
    WalletHistoryQuerySerializer,
    WalletSerializer,
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
            "payment.captured/failed, refund.processed/failed. Signed with "
            "X-Razorpay-Signature (HMAC-SHA256 of the body) and identified by "
            "X-Razorpay-Event-Id: each event is applied once; repeats answer "
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


# ---------- Payout accounts and the wallet (talent) ----------


class PayoutAccountView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="money_payout_account",
        summary="Your payout account",
        description="Masked. 404 until one is linked.",
        responses={200: PayoutAccountSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        account = PayoutAccount.objects.filter(talent=request.user).exclude(method="").first()
        if account is None:
            raise exceptions.NotFound("No payout account yet.")
        return Response(PayoutAccountSerializer(account).data)

    @extend_schema(
        operation_id="money_payout_account_link",
        summary="Add or change your payout account",
        description=(
            "A UPI id, or a bank account (number, IFSC, name on the account). The payout "
            "provider verifies it (a ₹1 deposit or an account check) before payouts use it: "
            "`validation_status` goes pending → verified or failed. Changing an account "
            "holds payouts for 24 hours and notifies you on every channel. Only a masked "
            "version is kept."
        ),
        request=LinkPayoutAccountSerializer,
        responses={
            200: PayoutAccountSerializer,
            400: ErrorSerializer,
            502: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def put(self, request: Request) -> Response:
        body = LinkPayoutAccountSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            account = payout_accounts.link(request.user, request=request, **body.validated_data)
        except payout_accounts.PayoutAccountError as exc:
            raise refuse(exc) from exc
        return Response(PayoutAccountSerializer(account).data)


class WalletView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="money_wallet",
        summary="Your wallet",
        description=(
            "Pending (held in escrow), available (released, not yet paid out), in transit, "
            "paid out, and TDS this financial year. Amounts in paise."
        ),
        responses={200: WalletSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(WalletSerializer(wallet.summary(request.user)).data)


class WalletHistoryView(generics.ListAPIView):
    permission_classes = [IsTalent]
    serializer_class = WalletEntrySerializer

    def get_queryset(self):
        query = WalletHistoryQuerySerializer(data=self.request.query_params)
        query.is_valid(raise_exception=True)
        try:
            return wallet.history(self.request.user, **query.validated_data)
        except wallet.WalletError as exc:
            raise refuse(exc) from exc

    @extend_schema(
        operation_id="money_wallet_history",
        summary="Your releases and payouts",
        description="Newest first. Filter by kind, status, dates (India) or financial year.",
        parameters=[WalletHistoryQuerySerializer],
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class WalletPayoutView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="money_wallet_request_payout",
        summary="Pay out what's available now",
        description=(
            "Starts a payout run for your available money. Payouts that must wait (no "
            "verified account, a recent account change, ID not verified) are held, and "
            "`held_reasons` says why. At most once every few minutes."
        ),
        request=None,
        responses={200: PayoutRunSerializer, 429: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        try:
            run = payouts.request_payout(request.user)
        except payouts.PayoutError as exc:
            raise refuse(exc) from exc
        return Response(PayoutRunSerializer(run).data)


FILE = {"csv": "text/csv; charset=utf-8", "pdf": "application/pdf"}


def _download(data: bytes, kind: str, name: str) -> HttpResponse:
    response = HttpResponse(data, content_type=FILE[kind])
    response["Content-Disposition"] = f'attachment; filename="{name}.{kind}"'
    response["Cache-Control"] = "private, no-store"
    return response


def _fy_or_400(fy: str) -> str:
    try:
        wallet.fy_bounds(fy)
    except wallet.WalletError as exc:
        raise refuse(exc) from exc
    return fy


class StatementView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="money_statement",
        summary="Your earnings statement for a financial year",
        description="Releases (gross, commission, GST, TDS, net) and their payouts. fy: 2026-27.",
        responses={200: StatementSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, fy: str) -> Response:
        return Response(StatementSerializer(wallet.statement(request.user, _fy_or_400(fy))).data)


class StatementFileView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="money_statement_file",
        summary="Download your statement (CSV or PDF)",
        responses={
            (200, "text/csv"): OpenApiTypes.BINARY,
            (200, "application/pdf"): OpenApiTypes.BINARY,
            400: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def get(self, request: Request, fy: str, kind: str) -> HttpResponse:
        if kind not in FILE:
            raise exceptions.NotFound("Ask for csv or pdf.")
        data = wallet.statement(request.user, _fy_or_400(fy))
        name = f"barterly-statement-{fy}"
        if kind == "csv":
            return _download(wallet.to_csv(data["rows"], wallet.STATEMENT_COLUMNS), kind, name)
        return _download(wallet.to_pdf("statement", data), kind, name)


class TdsView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="money_tds",
        summary="TDS deducted from you in a financial year",
        description=(
            "By quarter and by release, with the deductor's details. A summary for your "
            "records: the certificate itself is Form 16A."
        ),
        responses={200: TdsRecordSerializer, 400: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, fy: str) -> Response:
        return Response(TdsRecordSerializer(wallet.tds_record(request.user, _fy_or_400(fy))).data)


class TdsFileView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="money_tds_file",
        summary="Download your TDS summary (CSV or PDF)",
        responses={
            (200, "text/csv"): OpenApiTypes.BINARY,
            (200, "application/pdf"): OpenApiTypes.BINARY,
            400: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def get(self, request: Request, fy: str, kind: str) -> HttpResponse:
        if kind not in FILE:
            raise exceptions.NotFound("Ask for csv or pdf.")
        data = wallet.tds_record(request.user, _fy_or_400(fy))
        name = f"barterly-tds-{fy}"
        if kind == "csv":
            return _download(wallet.to_csv(data["rows"], wallet.TDS_COLUMNS), kind, name)
        return _download(wallet.to_pdf("tds", data), kind, name)


# ---------- Payout runs (admin) ----------


class PayoutRunsView(generics.ListAPIView):
    permission_classes = [IsAdminRole, _has_perm("money.view_payoutrun")]
    serializer_class = PayoutRunSerializer
    queryset = PayoutRun.objects.all()

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAdminRole(), _has_perm("money.run_payouts")()]
        return super().get_permissions()

    @extend_schema(
        operation_id="money_admin_payout_runs",
        summary="Payout runs (admin)",
        description="Newest first: what each run sent, held back (and why) and failed.",
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="money_admin_payout_run_start",
        summary="Start a payout run now (admin)",
        request=None,
        responses={201: PayoutRunDetailSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        run = payouts.run(PayoutTrigger.ADMIN, by=request.user)
        log_action(
            actor=request.user,
            action="money.payout_run_started",
            obj=run,
            after={"sent": run.sent, "held": run.held, "failed": run.failed},
            request=request,
        )
        return Response(PayoutRunDetailSerializer(run).data, status=status.HTTP_201_CREATED)


class PayoutRunDetailView(APIView):
    permission_classes = [IsAdminRole, _has_perm("money.view_payoutrun")]

    @extend_schema(
        operation_id="money_admin_payout_run",
        summary="One payout run and its payouts (admin)",
        responses={200: PayoutRunDetailSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, run_id: int) -> Response:
        run = PayoutRun.objects.filter(pk=run_id).first()
        if run is None:
            raise exceptions.NotFound("No such payout run.")
        return Response(PayoutRunDetailSerializer(run).data)


class PayoutsAdminView(generics.ListAPIView):
    permission_classes = [IsAdminRole, _has_perm("money.view_payout")]
    serializer_class = PayoutSerializer

    def get_queryset(self):
        rows = Payout.objects.select_related("escrow")
        if wanted := self.request.query_params.get("status"):
            rows = rows.filter(status=wanted)
        if self.request.query_params.get("needs_admin") in ("true", "1"):
            rows = rows.filter(status__in=("failed", "reversed"), next_attempt_at__isnull=True)
        return rows

    @extend_schema(
        operation_id="money_admin_payouts",
        summary="Payouts (admin)",
        description=(
            "Newest first. `status=failed` with `needs_admin=true` lists the payouts that "
            "ran out of automatic retries."
        ),
        parameters=[
            OpenApiParameter("status", str, enum=[c for c, _ in PayoutAttemptStatus.choices]),
            OpenApiParameter("needs_admin", bool),
        ],
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class PayoutRetryView(APIView):
    permission_classes = [IsAdminRole, _has_perm("money.run_payouts")]

    @extend_schema(
        operation_id="money_admin_payout_retry",
        summary="Retry a failed payout now (admin)",
        description="The latest failed attempt of an escrow; skips the back-off. Audited.",
        request=PayoutRetrySerializer,
        responses={
            200: PayoutRunDetailSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, payout_id) -> Response:
        body = PayoutRetrySerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            run = payouts.retry(payout_id, admin=request.user, note=body.validated_data["note"])
        except Payout.DoesNotExist as exc:
            raise exceptions.NotFound("No such payout.") from exc
        except payouts.PayoutError as exc:
            raise refuse(exc) from exc
        return Response(PayoutRunDetailSerializer(run).data)


class PayoutWebhookView(APIView):
    """RazorpayX calls this; the signature, not a user, is the credential."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="money_razorpayx_webhook",
        summary="RazorpayX payout events (webhook)",
        description=(
            "payout.processed/reversed/failed/rejected and fund_account.validation."
            "completed/failed. Signed with X-Razorpay-Signature; each X-Razorpay-Event-Id "
            "is applied once."
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
            outcome = payouts.handle_webhook(request.body, request.headers)
        except GatewayError as exc:
            raise WebhookRejected(str(exc)) from exc
        return Response({"outcome": outcome})
