from django.db.models import Prefetch
from drf_spectacular.utils import extend_schema, extend_schema_view
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.permissions import IsVendor
from apps.common.serializers import ErrorSerializer
from apps.properties.models import Property, PropertyPhoto
from apps.properties.serializers import (
    AddPhotoSerializer,
    PhotoSerializer,
    PropertySerializer,
    PublicPropertySerializer,
)
from apps.properties.services import add_photo, remove_property, save_property
from apps.verification.serializers import CaseSerializer
from apps.verification.views import case_response, run_service

TAG = ["properties"]
OWNER_ERRORS = {401: ErrorSerializer, 403: ErrorSerializer}


def _photos():
    return Prefetch("photos", queryset=PropertyPhoto.objects.select_related("media"))


class _OwnPropertyMixin:
    permission_classes = [IsVendor]

    def get_queryset(self):
        return Property.objects.filter(vendor=self.request.user).prefetch_related(_photos())

    def own_property(self, property_id) -> Property:
        return generics.get_object_or_404(self.get_queryset(), pk=property_id)


@extend_schema_view(
    get=extend_schema(
        operation_id="properties_list",
        summary="My properties",
        responses={200: PropertySerializer(many=True), **OWNER_ERRORS},
        tags=TAG,
    ),
    post=extend_schema(
        operation_id="properties_create",
        summary="Add a property",
        description=(
            "Without latitude/longitude the address is geocoded once (cached) to suggest a "
            "pin; the vendor confirms or moves it with PATCH."
        ),
        request=PropertySerializer,
        responses={201: PropertySerializer, 400: ErrorSerializer, **OWNER_ERRORS},
        tags=TAG,
    ),
)
class PropertyListCreateView(_OwnPropertyMixin, generics.ListCreateAPIView):
    serializer_class = PropertySerializer

    def create(self, request: Request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        prop = save_property(
            Property(vendor=request.user),
            serializer.validated_data,
            actor=request.user,
            request=request,
        )
        prop = self.get_queryset().get(pk=prop.pk)
        return Response(self.get_serializer(prop).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    get=extend_schema(
        operation_id="properties_retrieve",
        summary="One of my properties",
        responses={200: PropertySerializer, 404: ErrorSerializer, **OWNER_ERRORS},
        tags=TAG,
    ),
    patch=extend_schema(
        operation_id="properties_update",
        summary="Change a property",
        description=(
            "Changing the name, address or pin of a verified property sends it back to "
            "review and removes its verified status until approved again."
        ),
        request=PropertySerializer,
        responses={
            200: PropertySerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
            **OWNER_ERRORS,
        },
        tags=TAG,
    ),
    delete=extend_schema(
        operation_id="properties_destroy",
        summary="Remove a property",
        description="Soft delete. Its verification is withdrawn.",
        responses={204: None, 404: ErrorSerializer, **OWNER_ERRORS},
        tags=TAG,
    ),
)
class PropertyDetailView(_OwnPropertyMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = PropertySerializer
    lookup_url_kwarg = "property_id"
    http_method_names = ["get", "patch", "delete", "options"]

    def update(self, request: Request, *args, **kwargs) -> Response:
        prop = self.get_object()
        serializer = self.get_serializer(prop, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        save_property(prop, serializer.validated_data, actor=request.user, request=request)
        return Response(self.get_serializer(self.get_queryset().get(pk=prop.pk)).data)

    def perform_destroy(self, instance: Property) -> None:
        remove_property(instance, actor=self.request.user, request=self.request)


class PropertyPhotoListView(_OwnPropertyMixin, APIView):
    @extend_schema(
        operation_id="properties_photos_add",
        summary="Add a photo",
        description=(
            "Upload through /api/v1/media/upload-url/ and /api/v1/media/confirm/ (kind "
            "'photo') first. Send where the photo was taken (EXIF or device location): "
            "verification needs at least 3 photos taken within 500 m of the pin."
        ),
        request=AddPhotoSerializer,
        responses={
            201: PhotoSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
            **OWNER_ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, property_id) -> Response:
        prop = self.own_property(property_id)
        serializer = AddPhotoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        photo = add_photo(prop, **serializer.validated_data)
        photo = PropertyPhoto.objects.select_related("media").get(pk=photo.pk)
        return Response(PhotoSerializer(photo).data, status=status.HTTP_201_CREATED)


class PropertyPhotoDetailView(_OwnPropertyMixin, APIView):
    @extend_schema(
        operation_id="properties_photos_remove",
        summary="Remove a photo",
        description="The upload itself stays in your files.",
        responses={204: None, 404: ErrorSerializer, **OWNER_ERRORS},
        tags=TAG,
    )
    def delete(self, request: Request, property_id, photo_id) -> Response:
        prop = self.own_property(property_id)
        generics.get_object_or_404(prop.photos.all(), pk=photo_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PropertyVerificationView(_OwnPropertyMixin, APIView):
    @extend_schema(
        operation_id="properties_verification_submit",
        summary="Submit a property for verification",
        description=(
            "Needs the address, a confirmed pin in India, and at least 3 photos taken within "
            "500 m of it. The trust team reviews it; approval marks the property verified."
        ),
        request=None,
        responses={
            200: CaseSerializer,
            400: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            **OWNER_ERRORS,
        },
        tags=TAG,
    )
    def post(self, request: Request, property_id) -> Response:
        from apps.verification.services.checks import submit_property

        prop = self.own_property(property_id)
        return case_response(run_service(submit_property, request.user, prop, request=request))


class PublicPropertyView(generics.RetrieveAPIView):
    """Anyone may look. Only an approximate location unless they may see more."""

    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "property_public"
    serializer_class = PublicPropertySerializer
    lookup_url_kwarg = "property_id"

    def get_queryset(self):
        return Property.objects.prefetch_related(_photos())

    @extend_schema(
        operation_id="properties_public_retrieve",
        summary="A property's public page",
        description=(
            "No street address or exact pin: `approximate_location` is a fixed point within "
            "about 1 km. `exact_location` is filled only for the owner and admins (and, once "
            "bookings exist, guests with a confirmed booking)."
        ),
        responses={200: PublicPropertySerializer, 404: ErrorSerializer, 429: ErrorSerializer},
        tags=TAG,
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)
