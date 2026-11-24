from dataclasses import asdict

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import exceptions
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.appversions import services
from apps.appversions.models import Platform
from apps.appversions.serializers import (
    AppVersionQuerySerializer,
    AppVersionSerializer,
    AppVersionStatusSerializer,
    SetAppVersionSerializer,
)
from apps.common.permissions import IsStaffWith
from apps.common.serializers import ErrorSerializer

TAG = ["app versions"]


class AppVersionView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="app_version",
        summary="Minimum and latest app versions",
        description=(
            "The app calls this on launch. Below `minimum_version` it must block and send "
            "the person to `store_url`. Below `latest_version` it may offer the update.\n\n"
            "The app also sends `X-Client-Platform` and `X-Client-Version` on every call. "
            "When that version is below the minimum, **any** endpoint answers "
            "`426 Upgrade Required` with code `upgrade_required` and `details` holding "
            "`minimum_version` and `store_url` (docs/api-versioning.md). This endpoint and "
            "the health check never do."
        ),
        parameters=[
            OpenApiParameter("platform", enum=Platform.values, required=True),
            OpenApiParameter(
                "version", str, required=False, description="The app's version, e.g. 1.4.2."
            ),
        ],
        responses={200: AppVersionStatusSerializer, 400: ErrorSerializer},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        query = AppVersionQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        policy = services.policy_for(query.validated_data["platform"])
        version = query.validated_data.get("version")
        body = {**asdict(policy), "update": policy.status_of(version) if version else "none"}
        return Response(AppVersionStatusSerializer(body).data)


class AdminAppVersionListView(APIView):
    permission_classes = [IsStaffWith("appversions.set_app_version")]

    @extend_schema(
        operation_id="app_versions_admin_list",
        summary="App version policies (admin)",
        responses={200: AppVersionSerializer(many=True)},
        tags=TAG,
    )
    def get(self, request: Request) -> Response:
        policies = services.all_policies()
        return Response([AppVersionSerializer(asdict(policies[p])).data for p in sorted(policies)])


class AdminAppVersionView(APIView):
    permission_classes = [IsStaffWith("appversions.set_app_version")]

    @extend_schema(
        operation_id="app_versions_admin_set",
        summary="Set a platform's minimum and latest versions (admin)",
        description=(
            "Raising the minimum forces every older app to update before it can do "
            "anything. A reason is required; the change is audited. Takes effect on every "
            "instance within APP_VERSION_CACHE_SECONDS."
        ),
        request=SetAppVersionSerializer,
        responses={200: AppVersionSerializer, 400: ErrorSerializer, 404: ErrorSerializer},
        tags=TAG,
    )
    def put(self, request: Request, platform: str) -> Response:
        if platform not in Platform.values:
            raise exceptions.NotFound("No such platform.")
        serializer = SetAppVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            row = services.set_policy(
                platform, actor=request.user, request=request, **serializer.validated_data
            )
        except services.InvalidVersion as error:
            raise exceptions.ValidationError({"minimum_version": [str(error)]}) from error
        return Response(AppVersionSerializer(asdict(services.from_row(row))).data)
