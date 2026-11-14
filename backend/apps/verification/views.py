import uuid

from django.db.models import Prefetch
from drf_spectacular.utils import OpenApiParameter, OpenApiRequest, extend_schema
from rest_framework import exceptions, status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminRole, IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.verification.constants import CHECKS, BadgeKind, CaseStatus, CheckType
from apps.verification.models import Badge, VerificationCase, VerificationDocument
from apps.verification.providers.base import (
    InvalidWebhook,
    KycProviderError,
    KycProviderNotConfigured,
)
from apps.verification.serializers import (
    AdminCaseSerializer,
    BusinessCheckSerializer,
    CaseSerializer,
    CertificatesCheckSerializer,
    DecisionSerializer,
    MyVerificationSerializer,
    ReferenceCheckSerializer,
    StartIdCheckResponseSerializer,
    StartIdCheckSerializer,
    WebhookResponseSerializer,
)
from apps.verification.services import checks, kyc
from apps.verification.services.cases import CheckNotAvailable, InvalidTransition, decide
from apps.verification.throttles import KycStartThrottle

TAG = ["verification"]


class CheckNotAvailableError(exceptions.PermissionDenied):
    default_detail = "This check isn't available for your account."
    default_code = "check_not_available"


class CaseConflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The check can't change from its current status."
    default_code = "verification_conflict"


class KycUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "ID verification isn't available right now. Try again later."
    default_code = "kyc_unavailable"


class InvalidWebhookError(exceptions.APIException):
    # Not AuthenticationFailed: with no authenticators DRF would turn that into a 403.
    status_code = status.HTTP_401_UNAUTHORIZED
    default_detail = "Webhook signature check failed."
    default_code = "invalid_webhook"


def _with_documents(queryset):
    return queryset.prefetch_related(
        Prefetch("documents", queryset=VerificationDocument.objects.select_related("media"))
    )


def run_service(fn, *args, **kwargs):
    """Call a service, turning its domain errors into API errors."""
    try:
        return fn(*args, **kwargs)
    except CheckNotAvailable as exc:
        raise CheckNotAvailableError(str(exc)) from exc
    except InvalidTransition as exc:
        raise CaseConflict(str(exc)) from exc
    except KycProviderNotConfigured as exc:
        raise KycUnavailable from exc
    except KycProviderError as exc:
        raise KycUnavailable from exc


def case_response(case, code=status.HTTP_200_OK) -> Response:
    case = _with_documents(VerificationCase.objects).get(pk=case.pk)
    return Response(CaseSerializer(case).data, status=code)


_SUBMIT_ERRORS = {
    400: ErrorSerializer,
    401: ErrorSerializer,
    403: ErrorSerializer,
    409: ErrorSerializer,
}


class MyVerificationView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="verification_me",
        summary="My checks and badges",
        description=(
            "Every check that applies to your role with its cases (none until started; the "
            "property check has one per property), and your active badges."
        ),
        responses={200: MyVerificationSerializer, 401: ErrorSerializer},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        user = request.user
        cases: dict[str, list[VerificationCase]] = {}
        mine = _with_documents(VerificationCase.objects.filter(user=user)).order_by("created_at")
        for case in mine:
            cases.setdefault(case.check_type, []).append(case)
        badges = list(
            Badge.objects.filter(user=user, revoked_at__isnull=True).select_related("case")
        )
        rows = [
            {
                "check_type": check_type,
                "label": CheckType(check_type).label,
                "required": rule.required,
                "badge": rule.badge,
                "cases": cases.get(check_type, []),
            }
            for check_type, rule in CHECKS.get(user.role, {}).items()
        ]
        body = {
            "checks": rows,
            "badges": badges,
            "trusted_member": any(b.kind == BadgeKind.TRUSTED_MEMBER for b in badges),
        }
        return Response(MyVerificationSerializer(body).data)


class StartIdCheckView(APIView):
    permission_classes = [IsVendor | IsTalent]
    throttle_classes = [KycStartThrottle]

    @extend_schema(
        operation_id="verification_id_start",
        summary="Start an ID + selfie check",
        description=(
            "Opens a session with the KYC provider. Run the provider's capture flow with "
            "`client_token` (SDK) or `redirect_url` (hosted page); the result arrives by "
            "webhook. Images never pass through Barterly. Starting again on an approved "
            "check (new or changed ID) sends it back to review and removes the ID badge "
            "until approved."
        ),
        request=StartIdCheckSerializer,
        responses={
            201: StartIdCheckResponseSerializer,
            429: ErrorSerializer,
            503: ErrorSerializer,
            **_SUBMIT_ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = StartIdCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case, session = run_service(
            kyc.start_id_check,
            request.user,
            document_type=serializer.validated_data["document_type"],
            request=request,
        )
        case = _with_documents(VerificationCase.objects).get(pk=case.pk)
        body = {"case": case, "session": session}
        return Response(StartIdCheckResponseSerializer(body).data, status=status.HTTP_201_CREATED)


class BusinessCheckView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="verification_business_submit",
        summary="Submit PAN and GST for review",
        description=(
            "Formats are checked here (and that the GSTIN contains the PAN). Only the last "
            "four characters are stored. Changing the business name or GSTIN on an "
            "approved check sends it back to review."
        ),
        request=BusinessCheckSerializer,
        responses={200: CaseSerializer, **_SUBMIT_ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = BusinessCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        case = run_service(
            checks.submit_business, request.user, **serializer.validated_data, request=request
        )
        return case_response(case)


class SocialCheckView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="verification_social_submit",
        summary="Submit the Instagram account on my profile",
        description=(
            "The response's `details.bio_code` must be in the account's bio while the "
            "trust team checks it. Changing the handle on an approved check sends it back "
            "to review."
        ),
        request=None,
        responses={200: CaseSerializer, **_SUBMIT_ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        return case_response(run_service(checks.submit_social, request.user, request=request))


class CertificatesCheckView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="verification_certificates_submit",
        summary="Submit certificates (optional)",
        request=CertificatesCheckSerializer,
        responses={200: CaseSerializer, **_SUBMIT_ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = CertificatesCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        certs = [
            checks.Certificate(media_id=str(c["media_id"]), title=c["title"])
            for c in serializer.validated_data["certificates"]
        ]
        return case_response(
            run_service(
                checks.submit_certificates, request.user, certificates=certs, request=request
            )
        )


class ReferenceCheckView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="verification_reference_submit",
        summary="Submit one reference",
        request=ReferenceCheckSerializer,
        responses={200: CaseSerializer, **_SUBMIT_ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = ReferenceCheckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return case_response(
            run_service(
                checks.submit_reference, request.user, **serializer.validated_data, request=request
            )
        )


class KycWebhookView(APIView):
    """Called by the KYC provider, not by apps. Authenticated by its signature."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="verification_kyc_webhook",
        summary="KYC provider result (webhook)",
        description=(
            "Signed by the provider over the raw body; deliveries are de-duplicated by "
            "idempotency key, so retries are safe. `outcome` is applied, duplicate, "
            "pending, stale, ignored or unknown_reference."
        ),
        request=OpenApiRequest(request={"type": "object", "additionalProperties": True}),
        responses={
            200: WebhookResponseSerializer,
            401: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        body = request.body  # raw bytes: the signature covers exactly these
        try:
            outcome = kyc.handle_webhook(request.headers, body)
        except InvalidWebhook as exc:
            raise InvalidWebhookError from exc
        except KycProviderNotConfigured as exc:
            raise KycUnavailable from exc
        return Response({"outcome": outcome})


# --- Trust team ---


class AdminCaseListView(ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = AdminCaseSerializer

    def get_queryset(self):
        qs = _with_documents(VerificationCase.objects.select_related("user"))
        params = self.request.query_params
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        if params.get("check_type"):
            qs = qs.filter(check_type=params["check_type"])
        if params.get("user"):
            try:
                qs = qs.filter(user_id=uuid.UUID(params["user"]))
            except ValueError as exc:
                raise exceptions.ValidationError({"user": ["Not a valid user id."]}) from exc
        # Oldest submissions first: a review queue.
        return qs.order_by("submitted_at", "created_at")

    @extend_schema(
        operation_id="verification_admin_cases_list",
        summary="Review queue",
        parameters=[
            OpenApiParameter("status", enum=CaseStatus.values, required=False),
            OpenApiParameter("check_type", enum=CheckType.values, required=False),
            OpenApiParameter("user", type=str, required=False, description="User id."),
        ],
        responses={
            200: AdminCaseSerializer(many=True),
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
        },
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class AdminCaseDetailView(RetrieveAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = AdminCaseSerializer
    lookup_url_kwarg = "case_id"

    def get_queryset(self):
        return _with_documents(VerificationCase.objects.select_related("user"))

    @extend_schema(
        operation_id="verification_admin_case_retrieve",
        summary="One case with its evidence",
        responses={
            200: AdminCaseSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
        },
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class AdminDecisionView(APIView):
    permission_classes = [IsAdminRole]

    @extend_schema(
        operation_id="verification_admin_case_decide",
        summary="Decide on a case",
        description=(
            "start_review, approve, reject, request_changes (submitted or in-review "
            "cases), or revoke (approved cases). Approving grants the badge; leaving "
            "approved removes it. Every decision is audit-logged."
        ),
        request=DecisionSerializer,
        responses={
            200: AdminCaseSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=TAG,
    )
    def post(self, request: Request, case_id) -> Response:
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not VerificationCase.objects.filter(pk=case_id).exists():
            raise exceptions.NotFound("No such case.")
        try:
            case = run_service(
                decide,
                case_id,
                serializer.validated_data["decision"],
                reviewer=request.user,
                reason=serializer.validated_data.get("reason", ""),
                request=request,
            )
        except ValueError as exc:
            raise exceptions.ValidationError({"reason": [str(exc)]}) from exc
        case = _with_documents(VerificationCase.objects.select_related("user")).get(pk=case.pk)
        return Response(AdminCaseSerializer(case).data)
