from drf_spectacular.utils import extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.serializers import UserSerializer
from apps.common.serializers import ErrorSerializer


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="accounts_me",
        summary="The signed-in user",
        responses={200: UserSerializer, 403: ErrorSerializer},
        tags=["accounts"],
    )
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)
