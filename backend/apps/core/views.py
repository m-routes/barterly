from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.serializers import HealthSerializer
from apps.core.services.health import get_health_report


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="health_check",
        responses={200: HealthSerializer, 503: HealthSerializer},
        tags=["system"],
    )
    def get(self, request: Request) -> Response:
        report = get_health_report()
        code = status.HTTP_200_OK if report.ok else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response(HealthSerializer(report.as_dict()).data, status=code)
