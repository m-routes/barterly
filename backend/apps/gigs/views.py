from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import exceptions, generics, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminRole, IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.discovery.views import DISCOVER_SCHEMA, discover
from apps.gigs.constants import GigStatus
from apps.gigs.models import Gig
from apps.gigs.serializers import GigSerializer, StatusChangeSerializer
from apps.gigs.services import (
    GigLocked,
    InvalidGigTransition,
    PlanLimitReached,
    actor_for,
    create_gig,
    transition,
    update_gig,
)

TAG = ["gigs"]
ERRORS = {400: ErrorSerializer, 401: ErrorSerializer, 403: ErrorSerializer}


class GigConflict(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The gig can't do that from its current status."
    default_code = "gig_conflict"


class PlanLimitError(exceptions.PermissionDenied):
    default_detail = "Your plan allows no more live gigs."
    default_code = "plan_limit_reached"


def _gigs():
    return Gig.objects.select_related("property").prefetch_related("skills")


class GigCollectionView(generics.GenericAPIView):
    """GET: talent discover live gigs. POST: a vendor starts a gig."""

    serializer_class = GigSerializer

    def get_permissions(self):
        return [IsTalent()] if self.request.method == "GET" else [IsVendor()]

    @DISCOVER_SCHEMA
    def get(self, request: Request) -> Response:
        return discover(request)

    @extend_schema(
        operation_id="gigs_create",
        summary="Start a gig (as a draft)",
        description=(
            "Drafts may be incomplete. The full rules apply on submit: at most 6 hours a "
            "day and 6 days a week, a start date in the future, at least 1 slot, stay and "
            "meals for volunteer gigs, a deliverable for barter gigs, and a stipend above "
            "zero for hybrid and paid gigs."
        ),
        request=GigSerializer,
        responses={201: GigSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        gig = create_gig(request.user, serializer.validated_data, request=request)
        return Response(self.get_serializer(gig).data, status=status.HTTP_201_CREATED)


class MyGigsView(generics.ListAPIView):
    permission_classes = [IsVendor]
    serializer_class = GigSerializer

    def get_queryset(self):
        qs = _gigs().filter(vendor=self.request.user)
        wanted = self.request.query_params.get("status")
        return qs.filter(status=wanted) if wanted else qs

    @extend_schema(
        operation_id="gigs_mine_list",
        summary="My gigs (vendor)",
        parameters=[OpenApiParameter("status", enum=GigStatus.values, required=False)],
        responses={200: GigSerializer(many=True), **ERRORS},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)


@extend_schema_view(
    get=extend_schema(
        operation_id="gigs_retrieve",
        summary="One gig (its vendor or an admin)",
        responses={200: GigSerializer, 404: ErrorSerializer, **ERRORS},
        tags=TAG,
    ),
    patch=extend_schema(
        operation_id="gigs_update",
        summary="Edit a gig",
        description=(
            "Draft, in-review, live and paused gigs can be edited. Changing the pay, hours "
            "or dates of a live or paused gig sends it back to review."
        ),
        request=GigSerializer,
        responses={200: GigSerializer, 404: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    ),
)
class GigDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsVendor | IsAdminRole]
    serializer_class = GigSerializer
    lookup_url_kwarg = "gig_id"
    http_method_names = ["get", "patch", "options"]

    def get_queryset(self):
        if self.request.user.is_admin_role:
            return _gigs()
        return _gigs().filter(vendor=self.request.user)

    def update(self, request: Request, *args, **kwargs) -> Response:
        gig = self.get_object()
        if gig.vendor_id != request.user.pk:
            raise exceptions.PermissionDenied("Only the gig's vendor can edit it.")
        serializer = self.get_serializer(gig, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            gig = update_gig(gig.pk, serializer.validated_data, user=request.user, request=request)
        except GigLocked as exc:
            raise GigConflict(str(exc)) from exc
        return Response(self.get_serializer(gig).data)


class GigStatusView(APIView):
    permission_classes = [IsVendor | IsAdminRole]

    @extend_schema(
        operation_id="gigs_status_change",
        summary="Change a gig's status",
        description=(
            "Vendor: draft→in_review (submit), in_review→draft (withdraw), live→paused, "
            "paused→live, live/paused/filled→closed, draft/closed→archived. Admin: "
            "in_review→live (approve), in_review→draft (send back, with a reason), pause, "
            "close, archive. Filled, auto-close and re-review happen on their own."
        ),
        request=StatusChangeSerializer,
        responses={200: GigSerializer, 404: ErrorSerializer, 409: ErrorSerializer, **ERRORS},
        tags=TAG,
    )
    def post(self, request: Request, gig_id) -> Response:
        gig = generics.get_object_or_404(_gigs(), pk=gig_id)
        actor = actor_for(request.user, gig)
        if actor is None:
            raise exceptions.NotFound("No such gig.")
        serializer = StatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            gig = transition(
                gig.pk,
                serializer.validated_data["status"],
                actor=actor,
                user=request.user,
                reason=serializer.validated_data.get("reason", ""),
                request=request,
            )
        except InvalidGigTransition as exc:
            raise GigConflict(str(exc)) from exc
        except PlanLimitReached as exc:
            raise PlanLimitError(str(exc)) from exc
        except ValueError as exc:
            raise exceptions.ValidationError({"reason": [str(exc)]}) from exc
        return Response(GigSerializer(gig, context={"request": request}).data)


class AdminGigListView(generics.ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = GigSerializer

    def get_queryset(self):
        wanted = self.request.query_params.get("status") or GigStatus.IN_REVIEW
        return _gigs().filter(status=wanted).order_by("submitted_at", "created_at")

    @extend_schema(
        operation_id="gigs_admin_list",
        summary="Gig review queue",
        description="In-review gigs by default, oldest submission first.",
        parameters=[OpenApiParameter("status", enum=GigStatus.values, required=False)],
        responses={200: GigSerializer(many=True), 401: ErrorSerializer, 403: ErrorSerializer},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)
