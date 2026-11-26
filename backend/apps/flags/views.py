from drf_spectacular.utils import extend_schema
from rest_framework import exceptions
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsStaffWith
from apps.common.serializers import ErrorSerializer
from apps.flags import services
from apps.flags.registry import FLAGS
from apps.flags.serializers import FlagSerializer, FlagValuesSerializer, SetFlagSerializer

TAG = ["flags"]


class FlagValuesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="flags_values",
        summary="Which risky features are on",
        description=(
            "Apps hide a switched-off feature's entry points. The server enforces the "
            "flag regardless. Changes reach every instance within a minute."
        ),
        responses={200: FlagValuesSerializer},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        return Response(FlagValuesSerializer(services.all_flags()).data)


def _describe(key: str, enabled: bool) -> dict:
    flag = FLAGS[key]
    return {
        "key": key,
        "enabled": enabled,
        "description": flag.description,
        "when_off": flag.when_off,
    }


class AdminFlagListView(APIView):
    permission_classes = [IsStaffWith("flags.toggle_flag")]

    @extend_schema(
        operation_id="flags_admin_list",
        summary="Feature flags (admin)",
        responses={200: FlagSerializer(many=True)},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        values = services.all_flags()
        return Response([_describe(key, values[key]) for key in sorted(FLAGS)])


class AdminFlagView(APIView):
    permission_classes = [IsStaffWith("flags.toggle_flag")]

    @extend_schema(
        operation_id="flags_admin_set",
        summary="Turn a feature flag on or off (admin)",
        description="A reason is required; the change is audited.",
        request=SetFlagSerializer,
        responses={200: FlagSerializer, 404: ErrorSerializer},
        tags=TAG,
    )
    def post(self, request: Request, key: str) -> Response:
        if key not in FLAGS:
            raise exceptions.NotFound("No such flag.")
        serializer = SetFlagSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        flag = services.set_flag(
            key,
            serializer.validated_data["enabled"],
            actor=request.user,
            reason=serializer.validated_data["reason"],
            request=request,
        )
        return Response(_describe(key, flag.enabled))
