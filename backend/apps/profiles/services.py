"""Profile queries shared with other apps."""

from apps.accounts.models import Role
from apps.profiles.models import TalentProfile, VendorProfile

PROFILE_MODEL_FOR_ROLE = {Role.VENDOR: VendorProfile, Role.TALENT: TalentProfile}


def get_profile(user):
    """The user's live (not soft-deleted) profile for their role, or None."""
    model = PROFILE_MODEL_FOR_ROLE.get(user.role)
    if model is None:
        return None
    return model.objects.filter(user=user).first()


def is_profile_complete(user) -> bool:
    """True once the user has a role and a live profile with every required field.

    Admins have no marketplace profile, so theirs is always complete.
    """
    if user.role == Role.ADMIN:
        return True
    profile = get_profile(user)
    return profile is not None and profile.is_complete
