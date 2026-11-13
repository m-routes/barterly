"""Role and ownership permissions for DRF views.

Role checks require an authenticated, active user with that role. Combine with DRF
operators, e.g. `permission_classes = [IsVendor & IsOwner]` or `[IsAdminRole | IsOwner]`.
"""

from rest_framework.permissions import BasePermission

from apps.accounts.models import Role


class _HasRole(BasePermission):
    role: str = ""

    def has_permission(self, request, view) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and getattr(user, "role", None) == self.role
        )


class IsVendor(_HasRole):
    role = Role.VENDOR
    message = "This action is only available to vendors."


class IsTalent(_HasRole):
    role = Role.TALENT
    message = "This action is only available to talent."


class IsAdminRole(_HasRole):
    role = Role.ADMIN
    message = "This action is only available to Barterly admins."


class IsOwner(BasePermission):
    """Object-level: the object belongs to request.user.

    The view's `owner_field` names the path from the object to its owner, with `__`
    for nesting (default "user"; e.g. "listing__vendor"). Set it to "" when the object
    is the user itself.
    """

    message = "You do not have access to this object."

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj) -> bool:
        path = getattr(view, "owner_field", "user")
        owner = obj
        for part in path.split("__") if path else []:
            owner = getattr(owner, part, None)
            if owner is None:
                return False
        owner_pk = getattr(owner, "pk", owner)
        return owner_pk is not None and owner_pk == request.user.pk
