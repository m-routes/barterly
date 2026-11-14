"""Profile saves feed re-verification: compare watched fields before and after."""

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.profiles.models import TalentProfile, VendorProfile
from apps.verification.services.reverification import on_profile_changed, watched_fields

PROFILE_MODELS = (VendorProfile, TalentProfile)


def _fields(instance) -> list[str]:
    return sorted(watched_fields(instance.required_role))


@receiver(pre_save, sender=VendorProfile)
@receiver(pre_save, sender=TalentProfile)
def remember_verified_fields(sender, instance, raw=False, **kwargs):
    instance._verification_before = None
    if raw or instance._state.adding:
        return
    fields = _fields(instance)
    instance._verification_before = (
        sender.all_objects.filter(pk=instance.pk).values(*fields).first() if fields else None
    )


@receiver(post_save, sender=VendorProfile)
@receiver(post_save, sender=TalentProfile)
def reverify_changed_fields(sender, instance, created=False, raw=False, **kwargs):
    before = getattr(instance, "_verification_before", None)
    instance._verification_before = None
    if raw or created or not before:
        return
    changed = {name for name, old in before.items() if getattr(instance, name) != old}
    if changed:
        on_profile_changed(instance, changed)
