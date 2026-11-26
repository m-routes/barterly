"""The minimum and latest supported app versions, and the check that enforces them.

Reads are cached for APP_VERSION_CACHE_SECONDS, so a change reaches every instance
within that time without a deploy. Every change is audited with its reason.
"""

import re
from dataclasses import asdict, dataclass

from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from apps.appversions.models import AppVersionPolicy, Platform
from apps.common.services.audit import log_action

CACHE_KEY = "appversions:v1"
_VERSION = re.compile(r"^(\d{1,4})\.(\d{1,4})\.(\d{1,4})$")


class InvalidVersion(ValueError):
    pass


def parse(version: str) -> tuple[int, int, int] | None:
    """`1.4.2` → (1, 4, 2). Build suffixes (`+17`) and pre-releases (`-rc1`) are dropped."""
    core = (version or "").strip().split("+", 1)[0].split("-", 1)[0]
    match = _VERSION.match(core)
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[return-value]


@dataclass(frozen=True)
class Policy:
    platform: str
    minimum_version: str
    latest_version: str
    store_url: str
    message: str

    def status_of(self, version: str) -> str:
        """ "required", "available" or "none" for an app at `version`.

        An unparseable version is never blocked: a malformed header must not lock
        people out.
        """
        current = parse(version)
        if current is None:
            return "none"
        if current < parse(self.minimum_version):
            return "required"
        if current < parse(self.latest_version):
            return "available"
        return "none"


def _default(platform: str) -> Policy:
    values = settings.APP_VERSION_DEFAULTS[platform]
    return Policy(
        platform=platform,
        minimum_version=values["minimum_version"],
        latest_version=values["latest_version"],
        store_url=values["store_url"],
        message="",
    )


def from_row(row: AppVersionPolicy) -> Policy:
    return Policy(
        platform=row.platform,
        minimum_version=row.minimum_version,
        latest_version=row.latest_version,
        store_url=row.store_url or settings.APP_VERSION_DEFAULTS[row.platform]["store_url"],
        message=row.message,
    )


def all_policies() -> dict[str, Policy]:
    cached = cache.get(CACHE_KEY)
    if cached is not None:
        return {platform: Policy(**values) for platform, values in cached.items()}
    policies = {platform: _default(platform) for platform in Platform.values}
    policies.update({row.platform: from_row(row) for row in AppVersionPolicy.objects.all()})
    cache.set(
        CACHE_KEY,
        {platform: asdict(policy) for platform, policy in policies.items()},
        settings.APP_VERSION_CACHE_SECONDS,
    )
    return policies


def policy_for(platform: str) -> Policy:
    return all_policies()[platform]


def upgrade_required(platform: str, version: str) -> Policy | None:
    """The policy that blocks an app at `version` on `platform`, or None."""
    if platform not in Platform.values:
        return None
    policy = policy_for(platform)
    return policy if policy.status_of(version) == "required" else None


def set_policy(
    platform: str,
    *,
    minimum_version: str,
    latest_version: str,
    store_url: str = "",
    message: str = "",
    actor,
    reason: str,
    request=None,
) -> AppVersionPolicy:
    if platform not in Platform.values:
        raise InvalidVersion(f"Unknown platform {platform!r}.")
    minimum, latest = parse(minimum_version), parse(latest_version)
    if minimum is None or latest is None:
        raise InvalidVersion("Versions look like 1.4.2.")
    if latest < minimum:
        raise InvalidVersion("The latest version can't be older than the minimum.")
    if not reason.strip():
        raise ValueError("Say why the versions are changing.")
    with transaction.atomic():
        row = AppVersionPolicy.objects.select_for_update().filter(platform=platform).first()
        before = asdict(from_row(row) if row else _default(platform))
        if row is None:
            row = AppVersionPolicy(platform=platform)
        row.minimum_version = minimum_version.strip()
        row.latest_version = latest_version.strip()
        row.store_url = store_url.strip()
        row.message = message.strip()
        row.reason = reason.strip()
        row.updated_by = actor
        row.updated_at = timezone.now()
        row.save()
        after = {**asdict(from_row(row)), "reason": row.reason}
        log_action(
            actor=actor,
            action="appversions.changed",
            obj=row,
            before=before,
            after=after,
            request=request,
        )
        transaction.on_commit(lambda: cache.delete(CACHE_KEY))
    return row
