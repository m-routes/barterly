from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import exceptions, status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.common.permissions import IsTalent, IsVendor
from apps.common.serializers import ErrorSerializer
from apps.profiles.models import Skill, TalentProfile, VendorProfile
from apps.profiles.serializers import (
    SkillSerializer,
    TalentProfileSerializer,
    VendorProfileSerializer,
)


class ProfileNotFound(exceptions.NotFound):
    default_detail = "You haven't started your profile yet. PATCH it to create it."
    default_code = "profile_not_found"


class ProfileRemoved(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "This profile was removed. Contact support to restore it."
    default_code = "profile_removed"


class _MyProfileView(APIView):
    """GET the signed-in user's profile; PATCH creates it on first save."""

    model: type[VendorProfile] | type[TalentProfile]
    serializer_class: type

    def get(self, request: Request) -> Response:
        profile = self.model.objects.filter(user=request.user).first()
        if profile is None:
            raise ProfileNotFound
        return Response(self.serializer_class(profile, context={"request": request}).data)

    def patch(self, request: Request) -> Response:
        with transaction.atomic():
            # Lock the user so two first saves can't both create a profile.
            User.objects.select_for_update().filter(pk=request.user.pk).first()
            profile = self.model.objects.filter(user=request.user).first()
            if profile is None and self.model.all_objects.filter(user=request.user).exists():
                raise ProfileRemoved
            serializer = self.serializer_class(
                profile, data=request.data, partial=True, context={"request": request}
            )
            serializer.is_valid(raise_exception=True)
            if profile is None:
                serializer.save(user=request.user)
            else:
                serializer.save()
        code = status.HTTP_201_CREATED if profile is None else status.HTTP_200_OK
        return Response(serializer.data, status=code)


def _schema(serializer, tag_op: str, summary: str):
    responses = {
        200: serializer,
        401: ErrorSerializer,
        403: ErrorSerializer,
        404: ErrorSerializer,
    }
    return {
        "get": extend_schema(
            operation_id=f"{tag_op}_retrieve",
            summary=f"Get my {summary}",
            responses=responses,
            tags=["profiles"],
        ),
        "patch": extend_schema(
            operation_id=f"{tag_op}_update",
            summary=f"Create or update my {summary}",
            description=(
                "Partial update; the first PATCH creates the profile (201). The response "
                "says whether the profile is complete and which fields are missing."
            ),
            request=serializer,
            responses={
                200: serializer,
                201: serializer,
                400: ErrorSerializer,
                401: ErrorSerializer,
                403: ErrorSerializer,
                409: ErrorSerializer,
            },
            tags=["profiles"],
        ),
    }


_vendor = _schema(VendorProfileSerializer, "profiles_vendor_me", "vendor profile")
_talent = _schema(TalentProfileSerializer, "profiles_talent_me", "talent profile")


class MyVendorProfileView(_MyProfileView):
    permission_classes = [IsVendor]
    model = VendorProfile
    serializer_class = VendorProfileSerializer

    @_vendor["get"]
    def get(self, request: Request) -> Response:
        return super().get(request)

    @_vendor["patch"]
    def patch(self, request: Request) -> Response:
        return super().patch(request)


class MyTalentProfileView(_MyProfileView):
    permission_classes = [IsTalent]
    model = TalentProfile
    serializer_class = TalentProfileSerializer

    @_talent["get"]
    def get(self, request: Request) -> Response:
        return super().get(request)

    @_talent["patch"]
    def patch(self, request: Request) -> Response:
        return super().patch(request)


class SkillListView(ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = SkillSerializer
    pagination_class = None
    queryset = Skill.objects.filter(is_active=True)

    @extend_schema(
        operation_id="profiles_skills_list", summary="Skills talent can pick", tags=["profiles"]
    )
    def get(self, request: Request, *args, **kwargs) -> Response:
        return super().get(request, *args, **kwargs)
