from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, serializers, status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView

from apps.common.permissions import IsVendor
from apps.common.serializers import ErrorSerializer
from apps.geo.geocoders import GeocoderUnavailable
from apps.geo.services import MAX_QUERY_LENGTH, geocode


class GeocodeThrottle(UserRateThrottle):
    scope = "geocode"


class GeocodeRequestSerializer(serializers.Serializer):
    query = serializers.CharField(max_length=MAX_QUERY_LENGTH, help_text="A full address.")


class GeocodeResponseSerializer(serializers.Serializer):
    found = serializers.BooleanField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    display_name = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    postcode = serializers.CharField()


class GeocoderBusy(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Address lookup isn't available right now. Place the pin on the map instead."
    default_code = "geocoder_unavailable"


class GeocodeView(APIView):
    permission_classes = [IsVendor]
    throttle_classes = [GeocodeThrottle]

    @extend_schema(
        operation_id="geo_geocode",
        summary="Find an address on the map",
        description=(
            "For a 'find on map' button: call once when the vendor asks, never on each "
            "keystroke (OpenStreetMap's Nominatim policy forbids autocomplete). Answers are "
            "cached. Use the point to place a pin the vendor then confirms or moves."
        ),
        request=GeocodeRequestSerializer,
        responses={
            200: GeocodeResponseSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            429: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=["geo"],
    )
    def post(self, request: Request) -> Response:
        serializer = GeocodeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            result = geocode(serializer.validated_data["query"])
        except ValueError as exc:
            raise exceptions.ValidationError({"query": [str(exc)]}) from exc
        except GeocoderUnavailable as exc:
            raise GeocoderBusy from exc
        body = {
            "found": result.found,
            "latitude": float(result.latitude) if result.found else None,
            "longitude": float(result.longitude) if result.found else None,
            "display_name": result.display_name,
            "city": result.city,
            "state": result.state,
            "postcode": result.postcode,
        }
        return Response(GeocodeResponseSerializer(body).data)
