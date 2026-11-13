"""Sign-in: turn a verified OTP identity into a Barterly user and API tokens."""

import logging
from dataclasses import dataclass

from django.contrib.auth.hashers import make_password
from django.contrib.auth.models import update_last_login
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.auth.verifiers import VerifiedIdentity
from apps.accounts.models import Role, User
from apps.common.services.audit import log_action

logger = logging.getLogger(__name__)

# Roles a user may pick for themselves. Admin is granted only in the Django admin.
SELF_SERVICE_ROLES = (Role.VENDOR, Role.TALENT)


class AccountDisabled(Exception):
    pass


class RoleAlreadySet(Exception):
    pass


@dataclass(frozen=True)
class SignInResult:
    user: User
    created: bool
    access: str
    refresh: str


def sign_in(verified: VerifiedIdentity, *, request=None) -> SignInResult:
    """Fetch or create the user for a verified phone and issue a token pair."""
    with transaction.atomic():
        # No password: these users only ever sign in with an OTP.
        user, created = User.objects.get_or_create(
            phone=verified.phone, defaults={"password": make_password(None)}
        )
        if created:
            log_action(
                actor=user,
                action="user.signed_up",
                obj=user,
                after={"phone": user.phone, "provider": verified.provider},
                request=request,
            )
    if not user.is_active:
        raise AccountDisabled
    update_last_login(None, user)
    refresh = RefreshToken.for_user(user)
    logger.info(
        "User signed in",
        extra={"user_id": str(user.pk), "new_user": created, "provider": verified.provider},
    )
    return SignInResult(
        user=user, created=created, access=str(refresh.access_token), refresh=str(refresh)
    )


def choose_role(user: User, role: str, *, request=None) -> User:
    """Set the user's role the first time. Allowed once; admin is never self-service."""
    if role not in SELF_SERVICE_ROLES:
        raise ValueError(f"Role {role!r} can't be self-selected")
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        if locked.role:
            raise RoleAlreadySet
        locked.role = role
        locked.save(update_fields=["role", "updated_at"])
        log_action(
            actor=locked,
            action="user.role_selected",
            obj=locked,
            before={"role": ""},
            after={"role": role},
            request=request,
        )
    user.role = role
    return locked
