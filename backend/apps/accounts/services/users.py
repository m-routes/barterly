"""Account status and role changes. Every change here is audit-logged."""

from django.db import transaction

from apps.accounts.models import Role, User
from apps.common.services.audit import log_action

# Fields whose changes count as status changes and must be audited.
AUDITED_FIELDS = ("role", "is_active", "is_staff", "is_superuser")


def change_role(user: User, new_role: str, *, actor, request=None) -> User:
    if new_role not in Role.values:
        raise ValueError(f"Unknown role: {new_role!r}")
    return _update(
        user, {"role": new_role}, action="user.role_changed", actor=actor, request=request
    )


def set_active(user: User, active: bool, *, actor, request=None) -> User:
    action = "user.activated" if active else "user.deactivated"
    return _update(user, {"is_active": active}, action=action, actor=actor, request=request)


def audit_user_change(user: User, before: dict, *, actor, request=None) -> None:
    """Log audited fields that differ between `before` and the saved user (used by admin)."""
    changed = [f for f in AUDITED_FIELDS if f in before and before[f] != getattr(user, f)]
    if changed:
        log_action(
            actor=actor,
            action="user.updated",
            obj=user,
            before={f: before[f] for f in changed},
            after={f: getattr(user, f) for f in changed},
            request=request,
        )


def _update(user: User, values: dict, *, action: str, actor, request) -> User:
    with transaction.atomic():
        locked = User.objects.select_for_update().get(pk=user.pk)
        before = {field: getattr(locked, field) for field in values}
        if before == values:
            return locked
        for field, value in values.items():
            setattr(locked, field, value)
        locked.save(update_fields=[*values, "updated_at"])
        log_action(
            actor=actor, action=action, obj=locked, before=before, after=values, request=request
        )
    for field, value in values.items():
        setattr(user, field, value)
    return locked
