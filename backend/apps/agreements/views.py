"""Agreements: read them, open the PDF, sign, and change the terms by a new version."""

from django.db.models import Prefetch, Q
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.agreements import services
from apps.agreements.models import Agreement, AgreementVersion
from apps.agreements.serializers import (
    AgreementListItemSerializer,
    AgreementSerializer,
    ChallengeSerializer,
    DeclineChangeSerializer,
    PdfLinkSerializer,
    ProposeChangeSerializer,
    SignSerializer,
)
from apps.bookings.models import Booking
from apps.common.serializers import ErrorSerializer
from apps.offers.serializers import raw_object

TAG = ["agreements"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}
PDF_LINK_SECONDS = 600


class AgreementRefused(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_code = "agreement_refused"


def refuse(exc: services.AgreementError):
    error = AgreementRefused(exc.message)
    error.status_code = exc.status
    return error


def agreements_for(user):
    versions = AgreementVersion.objects.select_related("proposed_by").prefetch_related("signatures")
    return (
        Agreement.objects.filter(Q(booking__talent=user) | Q(booking__vendor=user))
        .select_related("booking__gig", "booking__talent", "booking__vendor", "current_version")
        .prefetch_related(Prefetch("versions", queryset=versions))
    )


def _respond(request, agreement_id, code=status.HTTP_200_OK) -> Response:
    agreement = agreements_for(request.user).get(pk=agreement_id)
    party = services.party_of(request.user, agreement.booking)
    data = AgreementSerializer(agreement, context={"request": request, "party": party}).data
    return Response(data, status=code)


def _version(user, version_id) -> AgreementVersion:
    qs = AgreementVersion.objects.select_related("agreement__booking__gig").filter(
        Q(agreement__booking__talent=user) | Q(agreement__booking__vendor=user)
    )
    return generics.get_object_or_404(qs, pk=version_id)


class AgreementListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AgreementListItemSerializer

    def get_queryset(self):
        return agreements_for(self.request.user).order_by("-created_at")

    @extend_schema(
        operation_id="agreements_list",
        summary="Your agreements",
        description="Newest first, with whether one is waiting for your signature.",
        tags=TAG,
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)


class BookingAgreementView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="agreements_for_booking",
        summary="A booking's agreement",
        description="Every version, newest first, with its signatures.",
        responses={200: AgreementSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, booking_id) -> Response:
        agreement = generics.get_object_or_404(agreements_for(request.user), booking_id=booking_id)
        return _respond(request, agreement.pk)


class AgreementDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="agreements_retrieve",
        summary="An agreement",
        responses={200: AgreementSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, agreement_id) -> Response:
        generics.get_object_or_404(agreements_for(request.user), pk=agreement_id)
        return _respond(request, agreement_id)


class PdfView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="agreements_pdf",
        summary="Open a version's PDF",
        description="A link valid for 10 minutes, with the SHA-256 the PDF must match.",
        responses={200: PdfLinkSerializer, 503: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, version_id) -> Response:
        version = _version(request.user, version_id)
        if not version.rendered:
            version = services.render_quietly(version.pk) or version
        try:
            url = services.signed_url(version)
        except services.AgreementError as exc:
            raise refuse(exc) from exc
        return Response(
            PdfLinkSerializer(
                {
                    "url": url,
                    "expires_in": PDF_LINK_SECONDS,
                    "sha256": version.pdf_sha256,
                    "size": version.pdf_size,
                }
            ).data
        )


class SignView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="agreements_sign_challenge",
        summary="What signing needs",
        description=(
            "The consent statement and how to prove it: method otp means re-run phone OTP "
            "sign-in just before signing and send the new ID token."
        ),
        responses={200: ChallengeSerializer, 409: ErrorSerializer, 503: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, version_id) -> Response:
        version = _version(request.user, version_id)
        try:
            challenge = services.challenge(version.pk, user=request.user)
        except services.AgreementError as exc:
            raise refuse(exc) from exc
        return Response(
            ChallengeSerializer(
                {
                    "method": challenge.method,
                    "consent_text": challenge.consent_text,
                    "phone_hint": challenge.phone_hint,
                    "max_age_seconds": challenge.max_age_seconds,
                    "document_sha256": version.pdf_sha256,
                }
            ).data
        )

    @extend_schema(
        operation_id="agreements_sign",
        summary="Sign a version",
        description=(
            "Records your consent with the time, IP address and device. The agreement is in "
            "force once both sides have signed the same version."
        ),
        request=SignSerializer,
        responses={
            200: AgreementSerializer,
            400: ErrorSerializer,
            409: ErrorSerializer,
            503: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, version_id) -> Response:
        version = _version(request.user, version_id)
        serializer = SignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            services.sign(
                version.pk,
                user=request.user,
                consent=data["consent"],
                document_sha256=data["document_sha256"],
                otp_token=data["otp_token"],
                request=request,
            )
        except services.AgreementError as exc:
            raise refuse(exc) from exc
        return _respond(request, version.agreement_id)


class ProposeChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="agreements_propose_change",
        summary="Change the terms",
        description=(
            "Draws up a new version with your changes. Both sides must sign it; until then "
            "the version in force stays in force. Dates can't change once the stay starts."
        ),
        request=ProposeChangeSerializer,
        responses={201: AgreementSerializer, 400: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, booking_id) -> Response:
        if not Booking.objects.filter(
            Q(talent=request.user) | Q(vendor=request.user), pk=booking_id
        ).exists():
            raise exceptions.NotFound("No such booking.")
        changes = raw_object(request.data, "changes")
        reason = request.data.get("reason", "")
        if not isinstance(reason, str) or len(reason) > 1000:
            raise exceptions.ValidationError({"reason": "Up to 1000 characters."})
        try:
            version = services.propose_change(
                booking_id, user=request.user, changes=changes, reason=reason, request=request
            )
        except services.AgreementError as exc:
            raise refuse(exc) from exc
        return _respond(request, version.agreement_id, status.HTTP_201_CREATED)


class DeclineChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="agreements_decline_change",
        summary="Decline a change",
        description="Turn down a new version (or withdraw your own). The version in force stays.",
        request=DeclineChangeSerializer,
        responses={200: AgreementSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, version_id) -> Response:
        version = _version(request.user, version_id)
        serializer = DeclineChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            services.decline_change(
                version.pk,
                user=request.user,
                reason=serializer.validated_data.get("reason", ""),
                request=request,
            )
        except services.AgreementError as exc:
            raise refuse(exc) from exc
        return _respond(request, version.agreement_id)
