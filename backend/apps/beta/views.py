from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.beta import rules
from apps.beta.serializers import BetaRulesSerializer


class BetaRulesView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        operation_id="beta_rules",
        summary="The closed-beta rules in force",
        description=(
            "Whether sign-up needs an invite code (and for which roles), and the beta's "
            "limits on live gigs per host and on one booking's stipend. Clients show the "
            "invite field and the limits from this; the server enforces them regardless."
        ),
        responses={200: BetaRulesSerializer},
        tags=["beta"],
    )
    def get(self, request: Request) -> Response:
        return Response(BetaRulesSerializer(rules.summary()).data)
