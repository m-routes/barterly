"""Privacy API: consents, export, correction, deletion, and the public documents and
grievance officer. Everything under /privacy/ acts on the signed-in person only."""

from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.serializers import ErrorSerializer
from apps.common.services.audit import log_action
from apps.privacy.errors import consent_error, service_error
from apps.privacy.models import (
    REQUIRED_PURPOSES,
    ConsentRecord,
    CorrectionRequest,
    DataExport,
    DeletionRequest,
    DeletionStatus,
    Purpose,
)
from apps.privacy.serializers import (
    ConsentChangeSerializer,
    ConsentRecordSerializer,
    ConsentStateSerializer,
    CorrectionCreateSerializer,
    CorrectionRequestSerializer,
    DataExportSerializer,
    DeletionCreateSerializer,
    DeletionRequestSerializer,
    DeletionStatusSerializer,
    ExportLinkSerializer,
    GrievanceOfficerSerializer,
    PolicyDocumentSerializer,
)
from apps.privacy.services import consents, erasure, exports

TAG = ["privacy"]
AUTH_ERRORS = {401: ErrorSerializer, 403: ErrorSerializer}
DOCUMENT_PATHS = {
    Purpose.TERMS: "/legal/terms",
    Purpose.PRIVACY: "/legal/privacy",
    Purpose.LOCATION: "/legal/privacy#location",
    Purpose.SOCIAL: "/legal/privacy#social",
    Purpose.MARKETING: "/legal/privacy#marketing",
}


def _states(user):
    return ConsentStateSerializer(
        [{**s.__dict__, "needs_renewal": s.needs_renewal} for s in consents.states(user)],
        many=True,
    ).data


class DocumentsView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="privacy_documents",
        summary="Current versions of the documents people consent to",
        responses={200: PolicyDocumentSerializer(many=True)},
        auth=[],
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        rows = [
            {
                "purpose": p.value,
                "label": p.label,
                "version": consents.current_version(p.value),
                "required": p in REQUIRED_PURPOSES,
                "web_path": DOCUMENT_PATHS[p],
            }
            for p in Purpose
        ]
        return Response(PolicyDocumentSerializer(rows, many=True).data)


class GrievanceOfficerView(APIView):
    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="privacy_grievance_officer",
        summary="How to reach the Grievance Officer",
        responses={200: GrievanceOfficerSerializer},
        auth=[],
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(GrievanceOfficerSerializer(settings.GRIEVANCE_OFFICER).data)


class ConsentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="privacy_consents",
        summary="My consents, one per purpose",
        responses={200: ConsentStateSerializer(many=True), **AUTH_ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(_states(request.user))

    @extend_schema(
        operation_id="privacy_consents_change",
        summary="Give or withdraw one consent",
        description=(
            "`granted: true` with the version shown gives consent; `granted: false` "
            "withdraws it, effective at once. Terms and privacy policy can't be withdrawn "
            "on their own (409 `consent_required`): delete the account instead. Every "
            "change is audit-logged. Returns all consents."
        ),
        request=ConsentChangeSerializer,
        responses={
            200: ConsentStateSerializer(many=True),
            400: ErrorSerializer,
            409: ErrorSerializer,
            **AUTH_ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        body = ConsentChangeSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        data = body.validated_data
        try:
            consents.record(
                request.user,
                data["purpose"],
                granted=data["granted"],
                version=data.get("version"),
                source=data["source"],
                request=request,
            )
        except consents.ConsentError as exc:
            raise consent_error(exc) from exc
        return Response(_states(request.user))


class ConsentHistoryView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = ConsentRecordSerializer

    def get_queryset(self):
        return ConsentRecord.objects.filter(user=self.request.user)

    @extend_schema(
        operation_id="privacy_consents_history",
        summary="Every consent I gave or withdrew, newest first",
        responses={200: ConsentRecordSerializer(many=True), **AUTH_ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class ExportsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DataExportSerializer

    def get_queryset(self):
        return DataExport.objects.filter(user=self.request.user)

    @extend_schema(
        operation_id="privacy_exports",
        summary="My data exports",
        responses={200: DataExportSerializer(many=True), **AUTH_ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="privacy_exports_create",
        summary="Export my data as JSON",
        description=(
            "Builds one machine-readable JSON file of everything Barterly holds about you "
            "and keeps it for a day. Fetch it with the export's link endpoint, which "
            "returns a signed URL valid for a few minutes. A few exports a day at most."
        ),
        request=None,
        responses={201: DataExportSerializer, 429: ErrorSerializer, **AUTH_ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        try:
            export = exports.create(request.user, request=request)
        except exports.ExportError as exc:
            raise service_error(exc) from exc
        return Response(DataExportSerializer(export).data, status=status.HTTP_201_CREATED)


class ExportLinkView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="privacy_exports_link",
        summary="A short-lived download link for one of my exports",
        request=None,
        responses={
            200: ExportLinkSerializer,
            404: ErrorSerializer,
            410: ErrorSerializer,
            **AUTH_ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, export_id) -> Response:
        export = DataExport.objects.filter(pk=export_id, user=request.user).first()
        if export is None:
            raise exceptions.NotFound("No such export.")
        try:
            url = exports.download_url(export, request=request)
        except exports.ExportError as exc:
            raise service_error(exc) from exc
        return Response(
            ExportLinkSerializer(
                {"url": url, "expires_in_seconds": settings.PRIVACY_EXPORT_URL_SECONDS}
            ).data
        )


class DeletionView(APIView):
    permission_classes = [IsAuthenticated]

    def _status(self, user):
        pending = DeletionRequest.objects.filter(user=user, status=DeletionStatus.SCHEDULED).first()
        return DeletionStatusSerializer(
            {
                "request": pending,
                "blockers": erasure.blockers(user),
                "grace_days": settings.PRIVACY_DELETION_GRACE_DAYS,
            }
        ).data

    @extend_schema(
        operation_id="privacy_deletion",
        summary="Whether my account is scheduled for deletion, and what blocks it",
        responses={200: DeletionStatusSerializer, **AUTH_ERRORS},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(self._status(request.user))

    @extend_schema(
        operation_id="privacy_deletion_request",
        summary="Delete my account",
        description=(
            "Schedules deletion after a grace period (cancel any time before). Then every "
            "personal field is erased; records the law makes us keep (payments, "
            "agreements, disputes, the audit log) stay, anonymised. 409 "
            "`deletion_blocked` lists what to finish first in `details.blockers`."
        ),
        request=DeletionCreateSerializer,
        responses={
            202: DeletionStatusSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            **AUTH_ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        body = DeletionCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            erasure.request_deletion(
                request.user, reason=body.validated_data.get("reason", ""), request=request
            )
        except erasure.ErasureError as exc:
            raise service_error(exc) from exc
        return Response(self._status(request.user), status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        operation_id="privacy_deletion_cancel",
        summary="Cancel my scheduled deletion",
        request=None,
        responses={200: DeletionRequestSerializer, 404: ErrorSerializer, **AUTH_ERRORS},
        tags=TAG,
    )
    def delete(self, request: Request) -> Response:
        try:
            entry = erasure.cancel_deletion(request.user, request=request)
        except erasure.ErasureError as exc:
            raise service_error(exc) from exc
        return Response(DeletionRequestSerializer(entry).data)


class CorrectionsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CorrectionRequestSerializer

    def get_queryset(self):
        return CorrectionRequest.objects.filter(user=self.request.user)

    @extend_schema(
        operation_id="privacy_corrections",
        summary="My correction requests",
        responses={200: CorrectionRequestSerializer(many=True), **AUTH_ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="privacy_corrections_create",
        summary="Ask us to correct something you can't edit yourself",
        description=(
            "Your profile is edited directly (PATCH /api/v1/profiles/.../me/). Use this "
            "for the rest: your phone number, a name on a signed agreement, a "
            "verification result. The team replies within the grievance timelines."
        ),
        request=CorrectionCreateSerializer,
        responses={201: CorrectionRequestSerializer, 400: ErrorSerializer, **AUTH_ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        body = CorrectionCreateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        with transaction.atomic():
            entry = CorrectionRequest.objects.create(user=request.user, **body.validated_data)
            log_action(
                actor=request.user,
                action="privacy.correction_requested",
                obj=entry,
                after={"field": entry.field, "status": entry.status},
                request=request,
            )
        return Response(CorrectionRequestSerializer(entry).data, status=status.HTTP_201_CREATED)
