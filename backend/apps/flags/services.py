"""Reading and changing feature flags.

Reads are cached for FLAG_CACHE_SECONDS, so a change reaches every instance within that
time without a deploy. Every change is audited with its reason.
"""

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.common.services.audit import log_action
from apps.flags.models import FeatureFlag
from apps.flags.registry import FLAGS

CACHE_KEY = "flags:v1"


class UnknownFlag(KeyError):
    pass


def all_flags() -> dict[str, bool]:
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return cached
    values = {key: flag.default for key, flag in FLAGS.items()}
    values.update(dict(FeatureFlag.objects.filter(key__in=FLAGS).values_list("key", "enabled")))
    cache.set(CACHE_KEY, values, settings.FLAG_CACHE_SECONDS)
    return values


def is_enabled(key: str) -> bool:
    if key not in FLAGS:
        raise UnknownFlag(key)
    return all_flags()[key]


def set_flag(key: str, enabled: bool, *, actor, reason: str, request=None) -> FeatureFlag:
    if key not in FLAGS:
        raise UnknownFlag(key)
    if not reason.strip():
        raise ValueError("Say why the flag is changing.")
    with transaction.atomic():
        flag = FeatureFlag.objects.select_for_update().filter(key=key).first()
        before = {"enabled": flag.enabled if flag else FLAGS[key].default}
        if flag is None:
            flag = FeatureFlag(key=key)
        flag.enabled = enabled
        flag.reason = reason.strip()
        flag.updated_by = actor
        flag.updated_at = timezone.now()
        flag.save()
        log_action(
            actor=actor,
            action="flags.changed",
            obj=flag,
            before=before,
            after={"enabled": enabled, "reason": flag.reason},
            request=request,
        )
        transaction.on_commit(lambda: cache.delete(CACHE_KEY))
    return flag
