from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.serializers import ErrorSerializer
from apps.media.models import MediaFile
from apps.media.serializers import (
    ConfirmRequestSerializer,
    MediaFileSerializer,
    UploadUrlRequestSerializer,
    UploadUrlResponseSerializer,
)
from apps.media.services.uploads import (
    UploadNotAllowed,
    UploadNotReady,
    UploadRejected,
    confirm_upload,
    prepare_upload,
)
from apps.media.storage import StorageNotConfigured
from apps.media.throttles import UploadUrlThrottle


class UploadNotAllowedError(exceptions.APIException):
    status_code = status.HTTP_400_BAD_REQUEST
    default_detail = "This upload isn't allowed."
    default_code = "upload_not_allowed"


class UploadNotReadyError(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The file hasn't arrived yet. Finish the upload, then confirm."
    default_code = "upload_not_found"


class UploadRejectedError(exceptions.APIException):
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "The uploaded file was rejected."
    default_code = "upload_rejected"


class StorageUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "File storage is not available."
    default_code = "media_storage_unavailable"


def _own_media(request: Request, media_id) -> MediaFile:
    media = MediaFile.objects.filter(pk=media_id).first()
    if media is None or not (media.owner_id == request.user.pk or request.user.is_admin_role):
        raise exceptions.NotFound("No such file.")
    return media


class UploadUrlView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [UploadUrlThrottle]

    @extend_schema(
        operation_id="media_upload_url",
        summary="Get a signed URL to upload one file",
        description=(
            "Allowed: avatar and photo (jpeg, png, webp; 5 MB and 10 MB), video (mp4, "
            "100 MB), document (pdf, jpeg, png; 10 MB). PUT the file to `upload_url` with "
            "exactly the returned `headers` before `expires_at`, then call "
            "/api/v1/media/confirm/."
        ),
        request=UploadUrlRequestSerializer,
        responses={
            201: UploadUrlResponseSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            429: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=["media"],
    )
    def post(self, request: Request) -> Response:
        serializer = UploadUrlRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            prepared = prepare_upload(owner=request.user, **serializer.validated_data)
        except UploadNotAllowed as exc:
            raise UploadNotAllowedError(str(exc)) from exc
        except StorageNotConfigured as exc:
            raise StorageUnavailable from exc
        body = {
            "media_id": prepared.media.pk,
            "upload_url": prepared.upload.url,
            "method": prepared.upload.method,
            "headers": prepared.upload.headers,
            "expires_at": prepared.upload.expires_at,
        }
        return Response(UploadUrlResponseSerializer(body).data, status=status.HTTP_201_CREATED)


class ConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="media_confirm",
        summary="Record an uploaded file",
        description=(
            "Checks the stored file against what was declared (type, size, checksum, file "
            "signature), records it, and starts processing (virus scan; resized copies for "
            "images). Safe to repeat."
        ),
        request=ConfirmRequestSerializer,
        responses={
            200: MediaFileSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            404: ErrorSerializer,
            409: ErrorSerializer,
            422: ErrorSerializer,
            503: ErrorSerializer,
        },
        tags=["media"],
    )
    def post(self, request: Request) -> Response:
        serializer = ConfirmRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        media = _own_media(request, serializer.validated_data["media_id"])
        if media.owner_id != request.user.pk:
            raise exceptions.NotFound("No such file.")
        try:
            media = confirm_upload(media, request=request)
        except UploadNotReady as exc:
            raise UploadNotReadyError from exc
        except UploadRejected as exc:
            raise UploadRejectedError(str(exc) or None) from exc
        except StorageNotConfigured as exc:
            raise StorageUnavailable from exc
        return Response(MediaFileSerializer(media).data)


class MediaDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="media_retrieve",
        summary="A file, with short-lived signed read URLs",
        description="Owner (or a Barterly admin) only. `url` is null until the file is ready.",
        responses={200: MediaFileSerializer, 401: ErrorSerializer, 404: ErrorSerializer},
        tags=["media"],
    )
    def get(self, request: Request, media_id) -> Response:
        media = _own_media(request, media_id)
        try:
            return Response(MediaFileSerializer(media).data)
        except StorageNotConfigured as exc:
            raise StorageUnavailable from exc
