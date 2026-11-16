from django.db.models import Count, F, Prefetch
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions, generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.applications.models import Application, ApplicationAttachment
from apps.applications.serializers import (
    ApplicationListItemSerializer,
    ApplicationSerializer,
    ApplySerializer,
    BlockedSerializer,
    VendorStatusSerializer,
    WithdrawSerializer,
)
from apps.applications.services import (
    ApplicationBlocked,
    AttachmentInput,
    InvalidApplicationTransition,
    apply,
    withdraw,
)
from apps.chat.services import with_chat
from apps.common.exceptions import error_body
from apps.common.permissions import IsAdminRole, IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.gigs.models import Gig
from apps.hiring import services as hiring
from apps.hiring.serializers import (
    VendorApplicationListItemSerializer,
    VendorApplicationSerializer,
)
from apps.verification.models import Badge

TAG = ["applications"]
ERRORS = {401: ErrorSerializer, 403: ErrorSerializer, 404: ErrorSerializer}
SORTS = {
    "fit": ("-fit_score", "-applied_at"),
    "newest": ("-applied_at",),
    "oldest": ("applied_at",),
}


class Conflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The application can't do that from its current status."
    default_code = "application_conflict"


def applications():
    """Everything the serializers read, in a fixed number of queries."""
    return (
        Application.objects.select_related("gig", "talent__talent_profile")
        .prefetch_related(
            "talent__talent_profile__skills",
            "talent__reliability_scores",
            Prefetch(
                "talent__badges",
                queryset=Badge.objects.filter(revoked_at__isnull=True),
                to_attr="active_badges",
            ),
        )
        .annotate(attachment_count=Count("attachments"))
    )


def with_attachments(qs):
    return qs.prefetch_related(
        Prefetch("attachments", queryset=ApplicationAttachment.objects.select_related("media"))
    )


class GigApplicationsView(generics.ListAPIView):
    """POST: talent apply. GET: the gig's vendor lists applicants (with their private
    tags and note counts)."""

    serializer_class = VendorApplicationListItemSerializer

    def get_permissions(self):
        return [IsTalent()] if self.request.method == "POST" else [IsVendor()]

    def get_queryset(self):
        gig = generics.get_object_or_404(Gig, pk=self.kwargs["gig_id"], vendor=self.request.user)
        qs = (
            with_chat(applications(), self.request.user)
            .annotate(agreement_ref=F("booking__agreement__id"))
            .filter(gig=gig)
            .prefetch_related("private_tags")
            .annotate(note_count=Count("private_notes", distinct=True))
        )
        params = self.request.query_params
        if params.get("tag"):
            qs = qs.filter(private_tags__label=params["tag"].strip().lower())
        if params.get("status"):
            qs = qs.filter(status__in=params["status"].split(","))
        if params.get("min_score"):
            try:
                qs = qs.filter(fit_score__gte=int(params["min_score"]))
            except ValueError as exc:
                raise exceptions.ValidationError({"min_score": ["Send a number."]}) from exc
        sort = params.get("sort", "fit")
        if sort not in SORTS:
            raise exceptions.ValidationError({"sort": [f"One of: {', '.join(SORTS)}."]})
        return qs.order_by(*SORTS[sort], "id")

    @extend_schema(
        operation_id="gig_applications_list",
        summary="Applicants for my gig (vendor)",
        description="Sorted by fit score by default. No contact details are shared.",
        parameters=[
            OpenApiParameter("status", str, description="Comma list of statuses."),
            OpenApiParameter("min_score", int),
            OpenApiParameter("tag", str, description="Only applicants with this private tag."),
            OpenApiParameter("sort", enum=list(SORTS)),
        ],
        responses={
            200: VendorApplicationListItemSerializer(many=True),
            400: ErrorSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)

    @extend_schema(
        operation_id="gig_applications_create",
        summary="Apply to a gig (talent)",
        description=(
            "Needs a complete profile, the gig's verification level, the gig's languages "
            "and follower minimum, dates inside the gig that meet its minimum stay, and "
            "an answer to every screening question. If anything fails, a 422 lists every "
            "reason in `details.reasons`. Attachments: up to 8 of your uploads or https "
            "links."
        ),
        request=ApplySerializer,
        responses={
            201: ApplicationSerializer,
            400: ErrorSerializer,
            422: BlockedSerializer,
            **ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, gig_id) -> Response:
        gig = generics.get_object_or_404(Gig, pk=gig_id)
        serializer = ApplySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            application = apply(
                request.user,
                gig.pk,
                pitch=data["pitch"],
                answers=data["answers"],
                proposed_start=data["proposed_start"],
                proposed_end=data["proposed_end"],
                attachments=[
                    AttachmentInput(
                        kind=a["kind"],
                        media_id=str(a["media_id"]) if a.get("media_id") else None,
                        url=a.get("url", ""),
                        title=a.get("title", ""),
                    )
                    for a in data["attachments"]
                ],
                request=request,
            )
        except ApplicationBlocked as exc:
            # The shared error shape, with every reason in details.
            body = error_body(
                "application_blocked",
                "You can't apply to this gig yet.",
                {"reasons": [r.as_dict() for r in exc.reasons]},
            )
            return Response(body, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        application = with_attachments(applications()).get(pk=application.pk)
        return Response(ApplicationSerializer(application).data, status=status.HTTP_201_CREATED)


class MyApplicationsView(generics.ListAPIView):
    permission_classes = [IsTalent]
    serializer_class = ApplicationListItemSerializer

    def get_queryset(self):
        return (
            with_chat(applications(), self.request.user)
            .annotate(agreement_ref=F("booking__agreement__id"))
            .filter(talent=self.request.user)
            .order_by("-applied_at", "id")
        )

    @extend_schema(
        operation_id="applications_mine_list",
        summary="My applications (talent)",
        responses={
            200: ApplicationListItemSerializer(many=True),
            401: ErrorSerializer,
            403: ErrorSerializer,
        },
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class ApplicationDetailView(generics.RetrieveAPIView):
    permission_classes = [IsTalent | IsVendor | IsAdminRole]
    serializer_class = ApplicationSerializer
    lookup_url_kwarg = "application_id"

    def get_serializer_class(self):
        # Vendors and admins also see private notes and tags; the applicant never does.
        user = self.request.user
        if user.is_authenticated and (user.is_vendor or user.is_admin_role):
            return VendorApplicationSerializer
        return ApplicationSerializer

    def get_queryset(self):
        user = self.request.user
        qs = with_attachments(applications())
        if user.is_admin_role:
            return qs
        if user.is_vendor:
            return qs.filter(gig__vendor=user).prefetch_related(
                "private_tags", "private_notes__author"
            )
        return qs.filter(talent=user)

    @extend_schema(
        operation_id="applications_retrieve",
        summary="One application",
        description=(
            "For the applicant, the gig's vendor, or an admin. Attachments have short-lived "
            "signed URLs. Badges show the applicant's verification; contact details are "
            "never included."
        ),
        responses={200: VendorApplicationSerializer, **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


class WithdrawView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="applications_withdraw",
        summary="Withdraw my application",
        description="Allowed while the application is active, up to accepting an offer.",
        request=WithdrawSerializer,
        responses={200: ApplicationSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            withdraw(
                application_id,
                talent=request.user,
                reason=serializer.validated_data.get("reason", ""),
                request=request,
            )
        except Application.DoesNotExist as exc:
            raise exceptions.NotFound("No such application.") from exc
        except InvalidApplicationTransition as exc:
            raise Conflict(str(exc)) from exc
        application = with_attachments(applications()).get(pk=application_id)
        return Response(ApplicationSerializer(application).data)


def _respond(application_id, *, vendor: bool = False) -> Response:
    application = with_attachments(applications()).get(pk=application_id)
    serializer = VendorApplicationSerializer if vendor else ApplicationSerializer
    return Response(serializer(application).data)


class VendorStatusView(APIView):
    permission_classes = [IsVendor]

    @extend_schema(
        operation_id="applications_status_change",
        summary="Shortlist, interview or reject",
        description=(
            "The gig's vendor moves an application along. Rejecting needs a reason_code "
            "(GET /api/v1/hiring/rejection-reasons/); the applicant reads its text and the "
            "optional message. Offers carry terms, so they have their own endpoint: "
            "POST /api/v1/applications/{id}/offer/."
        ),
        request=VendorStatusSerializer,
        responses={200: VendorApplicationSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        if not Application.objects.filter(pk=application_id, gig__vendor=request.user).exists():
            raise exceptions.NotFound("No such application.")
        serializer = VendorStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            hiring.move(
                application_id,
                data["status"],
                vendor=request.user,
                code=data.get("reason_code", ""),
                message=data.get("message", ""),
                request=request,
            )
        except hiring.HiringError as exc:
            raise Conflict(str(exc)) from exc
        return _respond(application_id, vendor=True)


class DeclineView(APIView):
    permission_classes = [IsTalent]

    @extend_schema(
        operation_id="applications_decline",
        summary="Decline an offer",
        description="Declines the host's offer waiting for your answer (see offers_decline).",
        request=WithdrawSerializer,
        responses={200: ApplicationSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, application_id) -> Response:
        if not Application.objects.filter(pk=application_id, talent=request.user).exists():
            raise exceptions.NotFound("No such application.")
        serializer = WithdrawSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.offers import services as offers
        from apps.offers.models import Party

        offer = offers.open_offer(application_id)
        if offer is None or offer.proposed_by != Party.VENDOR:
            raise Conflict("There's no offer waiting for your answer.")
        try:
            offers.decline(
                offer.pk,
                user=request.user,
                reason=serializer.validated_data.get("reason", ""),
                request=request,
            )
        except offers.OfferError as exc:
            raise Conflict(exc.message) from exc
        return _respond(application_id)
