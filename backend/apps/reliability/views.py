from drf_spectacular.utils import extend_schema
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reliability.models import ReliabilityScore, Side
from apps.reliability.score import Inputs, score
from apps.reliability.serializers import ReliabilityDetailSerializer


class MyReliabilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        operation_id="reliability_me",
        summary="Your reliability score on each side, with how it is made up",
        responses=ReliabilityDetailSerializer(many=True),
        tags=["reliability"],
    )
    def get(self, request: Request) -> Response:
        stored = {r.side: r for r in ReliabilityScore.objects.filter(user=request.user)}
        return Response(
            ReliabilityDetailSerializer(
                [_row(side, stored.get(side)) for side in Side.values], many=True
            ).data
        )


def _row(side: str, record: ReliabilityScore | None) -> dict:
    if record is None:
        result = score(Inputs())
        return {
            "side": side,
            "score": result.score,
            "level": result.level,
            "version": result.version,
            "inputs": Inputs().__dict__,
            "breakdown": result.breakdown,
        }
    return {
        "side": side,
        "score": record.score,
        "level": record.level,
        "version": record.version,
        "inputs": record.inputs,
        "breakdown": record.breakdown,
    }
