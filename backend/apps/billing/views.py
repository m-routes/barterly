from datetime import timedelta

from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.billing import entitlements, services
from apps.billing.gateway.base import GatewayError
from apps.billing.models import Invoice, Plan
from apps.billing.serializers import (
    BillingOverviewSerializer,
    CancelSubscriptionSerializer,
    ChangePlanSerializer,
    InvoicePdfLinkSerializer,
    InvoiceSerializer,
    PlanSerializer,
    SubscribeSerializer,
    SubscriptionSerializer,
)
from apps.common.permissions import IsVendor
from apps.common.serializers import ErrorSerializer
from apps.media.storage import get_storage

TAG = ["billing"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer}


class BillingRefused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "billing_refused"


def refuse(exc: services.BillingError):
    if exc.status == 400:
        return exceptions.ValidationError({"detail": exc.message})
    error = BillingRefused(exc.message)
    error.status_code = exc.status
    return error


def overview(vendor) -> dict:
    return {
        "subscription": entitlements.current_subscription(vendor),
        "entitlements": entitlements.summary(vendor),
    }


class PlansView(generics.ListAPIView):
    permission_classes = [IsVendor]
    serializer_class = PlanSerializer
    pagination_class = None
    queryset = Plan.objects.filter(is_public=True)

    @extend_schema(
        operation_id="billing_plans",
        summary="The plans on offer",
        description="Prices are per month in paise, before GST.",
        responses={200: PlanSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class OverviewView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="billing_overview",
        summary="My subscription and what my plan allows",
        responses={200: BillingOverviewSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(BillingOverviewSerializer(overview(request.user)).data)


class SubscribeView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="billing_subscribe",
        summary="Start a subscription (returns the hosted checkout link)",
        description=(
            "Send the vendor to `checkout_url` to pay. A coupon (or the launch trial) "
            "sets the card up now and starts charging when the trial ends."
        ),
        request=SubscribeSerializer,
        responses={
            201: SubscriptionSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            502: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = SubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            subscription = services.subscribe(
                request.user,
                plan_code=serializer.validated_data["plan"],
                coupon_code=serializer.validated_data.get("coupon", ""),
                request=request,
            )
        except services.BillingError as exc:
            raise refuse(exc) from exc
        return Response(SubscriptionSerializer(subscription).data, status=status.HTTP_201_CREATED)


class ChangePlanView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="billing_change_plan",
        summary="Upgrade now, or downgrade at the end of the period",
        description=(
            "Downgrading keeps live gigs running; new ones over the new limit are refused."
        ),
        request=ChangePlanSerializer,
        responses={
            200: SubscriptionSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            502: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = ChangePlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            subscription = services.change_plan(
                request.user, plan_code=serializer.validated_data["plan"], request=request
            )
        except services.BillingError as exc:
            raise refuse(exc) from exc
        return Response(SubscriptionSerializer(subscription).data)


class CancelView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="billing_cancel",
        summary="Cancel the subscription (at the end of the period by default)",
        request=CancelSubscriptionSerializer,
        responses={
            200: SubscriptionSerializer,
            409: ErrorSerializer,
            502: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = CancelSubscriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            subscription = services.cancel(
                request.user,
                at_period_end=serializer.validated_data["at_period_end"],
                request=request,
            )
        except services.BillingError as exc:
            raise refuse(exc) from exc
        return Response(SubscriptionSerializer(subscription).data)


class InvoicesView(generics.ListAPIView):
    permission_classes = [IsVendor]
    serializer_class = InvoiceSerializer

    def get_queryset(self):
        return Invoice.objects.filter(vendor=self.request.user)

    @extend_schema(
        operation_id="billing_invoices",
        summary="My GST invoices, newest first",
        responses={200: InvoiceSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class InvoicePdfView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="billing_invoice_pdf",
        summary="A short-lived link to the invoice PDF",
        responses={
            200: InvoicePdfLinkSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def get(self, request: Request, invoice_id) -> Response:
        invoice = generics.get_object_or_404(
            Invoice.objects.filter(vendor=request.user), pk=invoice_id
        )
        if not invoice.pdf_key:
            raise BillingRefused("The PDF is still being prepared. Try again in a moment.")
        expires = timedelta(minutes=10)
        url = get_storage().signed_read_url(
            invoice.pdf_key,
            expires=expires,
            download_name=f"{invoice.number.replace('/', '-')}.pdf",
        )
        return Response({"url": url, "expires_in": int(expires.total_seconds())})


class WebhookRejected(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_webhook"


class RazorpayWebhookView(APIView):
    """Razorpay calls this; the signature, not a user, is the credential."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = []

    @extend_schema(
        operation_id="billing_razorpay_webhook",
        summary="Razorpay subscription events (webhook)",
        description=(
            "Signed with X-Razorpay-Signature (HMAC-SHA256 of the body). Each event is "
            "applied once; repeats answer 200 and change nothing."
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
            outcome = services.handle_webhook(request.body, request.headers)
        except GatewayError as exc:
            raise WebhookRejected(str(exc)) from exc
        return Response({"outcome": outcome})
