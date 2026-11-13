import logging

from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import exceptions, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from apps.accounts.auth.verifiers import InvalidSignInToken, VerifierUnavailable, get_verifier
from apps.accounts.serializers import (
    ChooseRoleSerializer,
    ExchangeRequestSerializer,
    ExchangeResponseSerializer,
    RefreshRequestSerializer,
    TokenPairSerializer,
    UserSerializer,
)
from apps.accounts.services.auth import AccountDisabled, RoleAlreadySet, choose_role, sign_in
from apps.accounts.throttles import ExchangeIPThrottle, ExchangePhoneThrottle
from apps.common.serializers import ErrorSerializer
from apps.profiles.services import is_profile_complete

logger = logging.getLogger(__name__)


class InvalidSignIn(exceptions.AuthenticationFailed):
    default_detail = "The sign-in token is invalid or expired. Sign in again."
    default_code = "invalid_sign_in_token"


class AccountDisabledError(exceptions.PermissionDenied):
    default_detail = "This account has been disabled. Contact support."
    default_code = "account_disabled"


class ProviderUnavailable(exceptions.APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Sign-in is temporarily unavailable. Try again shortly."
    default_code = "auth_provider_unavailable"


class RoleAlreadySetError(exceptions.APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "Your role is already set. Contact support to change it."
    default_code = "role_already_set"


class _TokenEndpoint(APIView):
    """No request authentication, but failures are still 401 with a Bearer challenge
    (DRF turns 401 into 403 when a view has no authenticate header)."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request: Request) -> str:
        return 'Bearer realm="api"'


class ExchangeView(_TokenEndpoint):
    """Swap a Firebase phone-auth ID token for Barterly API tokens."""

    throttle_classes = [ExchangeIPThrottle]

    @extend_schema(
        operation_id="auth_exchange",
        summary="Exchange an OTP provider ID token for API tokens",
        description=(
            "Verifies the ID token from Firebase phone sign-in, creates the user on first "
            "sign-in, and returns a short-lived access token and a refresh token. "
            "Rate limited per IP and per phone number."
        ),
        request=ExchangeRequestSerializer,
        responses={
            200: ExchangeResponseSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            403: ErrorSerializer,
            429: ErrorSerializer,
            503: ErrorSerializer,
        },
        auth=[],
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = ExchangeRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            verified = get_verifier().verify(serializer.validated_data["id_token"])
        except InvalidSignInToken as exc:
            logger.info("Rejected sign-in token", extra={"reason": str(exc)})
            raise InvalidSignIn from exc
        except VerifierUnavailable as exc:
            logger.error("OTP provider unavailable", exc_info=exc)
            raise ProviderUnavailable from exc

        request.verified_phone = verified.phone
        phone_throttle = ExchangePhoneThrottle()
        if not phone_throttle.allow_request(request, self):
            self.throttled(request, phone_throttle.wait())

        try:
            result = sign_in(verified, request=request)
        except AccountDisabled as exc:
            raise AccountDisabledError from exc
        user = result.user
        body = {
            "access": result.access,
            "refresh": result.refresh,
            "is_new_user": result.created,
            "profile_complete": is_profile_complete(user),
            "needs_role": not user.role,
            "user": UserSerializer(user).data,
        }
        return Response(body)


class RefreshView(TokenRefreshView):
    """Rotating refresh: the old refresh token is blacklisted once used."""

    @extend_schema(
        operation_id="auth_refresh",
        summary="Get a new access token (and a new refresh token)",
        request=RefreshRequestSerializer,
        responses={200: TokenPairSerializer, 400: ErrorSerializer, 401: ErrorSerializer},
        auth=[],
        tags=["auth"],
    )
    def post(self, request: Request, *args, **kwargs) -> Response:
        return super().post(request, *args, **kwargs)


class LogoutView(_TokenEndpoint):
    """Revoke a refresh token. Holding the token is proof enough, so no access token is
    needed (it may already have expired)."""

    @extend_schema(
        operation_id="auth_logout",
        summary="Sign out by blacklisting the refresh token",
        request=RefreshRequestSerializer,
        responses={
            204: OpenApiResponse(description="Signed out."),
            400: ErrorSerializer,
            401: ErrorSerializer,
        },
        auth=[],
        tags=["auth"],
    )
    def post(self, request: Request) -> Response:
        serializer = RefreshRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            RefreshToken(serializer.validated_data["refresh"]).blacklist()
        except TokenError as exc:
            raise exceptions.AuthenticationFailed(str(exc), code="token_not_valid") from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="accounts_me",
        summary="The signed-in user",
        responses={200: UserSerializer, 401: ErrorSerializer, 403: ErrorSerializer},
        tags=["accounts"],
    )
    def get(self, request: Request) -> Response:
        return Response(UserSerializer(request.user).data)


class MeRoleView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="accounts_me_role",
        summary="Choose vendor or talent (once)",
        description=(
            "Sets the role of a user who signed up by OTP. Allowed once; admin roles are "
            "granted only in the Django admin."
        ),
        request=ChooseRoleSerializer,
        responses={
            200: UserSerializer,
            400: ErrorSerializer,
            401: ErrorSerializer,
            409: ErrorSerializer,
        },
        tags=["accounts"],
    )
    def post(self, request: Request) -> Response:
        serializer = ChooseRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            user = choose_role(request.user, serializer.validated_data["role"], request=request)
        except RoleAlreadySet as exc:
            raise RoleAlreadySetError from exc
        return Response(UserSerializer(user).data)
