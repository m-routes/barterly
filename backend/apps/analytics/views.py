from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.analytics import services
from apps.analytics.serializers import (
    AnalyticsEventBatchResultSerializer,
    AnalyticsEventBatchSerializer,
)
from apps.common.serializers import ErrorSerializer


class AnalyticsThrottle(UserRateThrottle):
    scope = "analytics"


class EventBatchView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [AnalyticsThrottle]

    @extend_schema(
        operation_id="analytics_events",
        summary="Send product events (only kept with analytics consent)",
        description=(
            "Up to 50 events per call. Without the person's analytics consent nothing is "
            "kept and `consent` is false. Unknown events and properties are dropped; see "
            "apps/analytics/events.py for the list. No personal data is stored: the "
            "person is a keyed hash, with no IP or device id."
        ),
        request=AnalyticsEventBatchSerializer,
        responses={
            202: AnalyticsEventBatchResultSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
        },
        tags=["analytics"],
    )
    def post(self, request: Request) -> Response:
        serializer = AnalyticsEventBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = services.ingest(
            request.user,
            data["events"],
            platform=data["platform"],
            app_version=data.get("app_version", ""),
        )
        return Response(AnalyticsEventBatchResultSerializer(result).data, status=202)
