"""Profile queries shared with other apps."""

from apps.accounts.models import Role
from apps.profiles.models import TalentProfile, VendorProfile

_PROFILE_FOR_ROLE = {Role.VENDOR: VendorProfile, Role.TALENT: TalentProfile}


def is_profile_complete(user) -> bool:
    """True once the user has a role and, for vendor or talent, a live profile.

    Admins have no marketplace profile, so theirs is always complete. Soft-deleted
    profiles don't count.
    """
    if user.role == Role.ADMIN:
        return True
    model = _PROFILE_FOR_ROLE.get(user.role)
    return model is not None and model.objects.filter(user=user).exists()
