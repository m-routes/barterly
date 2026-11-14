from django.db.models import Count, Prefetch
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
    WithdrawSerializer,
)
from apps.applications.services import (
    ApplicationBlocked,
    AttachmentInput,
    InvalidApplicationTransition,
    apply,
    withdraw,
)
from apps.common.exceptions import error_body
from apps.common.permissions import IsAdminRole, IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.gigs.models import Gig
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
    """POST: talent apply. GET: the gig's vendor lists applicants."""

    serializer_class = ApplicationListItemSerializer

    def get_permissions(self):
        return [IsTalent()] if self.request.method == "POST" else [IsVendor()]

    def get_queryset(self):
        gig = generics.get_object_or_404(Gig, pk=self.kwargs["gig_id"], vendor=self.request.user)
        qs = applications().filter(gig=gig)
        params = self.request.query_params
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
            OpenApiParameter("sort", enum=list(SORTS)),
        ],
        responses={200: ApplicationListItemSerializer(many=True), 400: ErrorSerializer, **ERRORS},
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
        return applications().filter(talent=self.request.user).order_by("-applied_at", "id")

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

    def get_queryset(self):
        user = self.request.user
        qs = with_attachments(applications())
        if user.is_admin_role:
            return qs
        if user.is_vendor:
            return qs.filter(gig__vendor=user)
        return qs.filter(talent=user)

    @extend_schema(
        operation_id="applications_retrieve",
        summary="One application",
        description=(
            "For the applicant, the gig's vendor, or an admin. Attachments have short-lived "
            "signed URLs. Badges show the applicant's verification; contact details are "
            "never included."
        ),
        responses={200: ApplicationSerializer, **ERRORS},
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
