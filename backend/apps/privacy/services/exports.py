"""Export my data: one machine-readable JSON file, fetched through a short-lived link.

The file is written to the media bucket under exports/<user>/<export>.json and deleted
after PRIVACY_EXPORT_KEEP_HOURS (expire_due, run by the privacy_retention job). Each
download link is signed for PRIVACY_EXPORT_URL_SECONDS only; ask for a new link while
the export is ready.
"""

import json
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import transaction
from django.utils import timezone

from apps.common.services.audit import log_action
from apps.media.storage import get_storage
from apps.privacy.models import DataExport, ExportStatus
from apps.privacy.services.registry import ALWAYS_EXCLUDED, EXPORT_SECTIONS, Section

FORMAT_VERSION = 1
USER_FIELDS = ("id", "phone", "email", "role", "is_active", "created_at", "last_login")


class ExportError(Exception):
    def __init__(self, code: str, message: str, status: int = 409):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def _row(obj, section: Section) -> dict:
    skip = ALWAYS_EXCLUDED | set(section.exclude)
    data = {}
    for f in obj._meta.concrete_fields:
        if f.name in skip:
            continue
        data[f.name if not f.is_relation else f.attname] = getattr(obj, f.attname)
    return data


def collect(user) -> dict:
    """Everything we hold about `user`, section by section."""
    data: dict = {
        "format_version": FORMAT_VERSION,
        "generated_at": timezone.now(),
        "account": {name: getattr(user, name) for name in USER_FIELDS},
    }
    for section in EXPORT_SECTIONS:
        model = apps.get_model(section.model)
        manager = getattr(model, "all_objects", model._default_manager)
        rows = manager.filter(**{section.path: user}, **section.only_if).order_by("pk")
        data[section.name] = [_row(obj, section) for obj in rows]
    profile = apps.get_model("profiles.TalentProfile").all_objects.filter(user=user).first()
    if profile is not None and data["talent_profile"]:
        data["talent_profile"][0]["skills"] = list(profile.skills.values_list("name", flat=True))
    return data


def render(user) -> bytes:
    return json.dumps(collect(user), cls=DjangoJSONEncoder, indent=2, sort_keys=True).encode()


def create(user, *, request=None, now=None) -> DataExport:
    now = now or timezone.now()
    since = now - timedelta(days=1)
    if (
        DataExport.objects.filter(user=user, created_at__gte=since).count()
        >= settings.PRIVACY_EXPORTS_PER_DAY
    ):
        raise ExportError(
            "export_limit", "You've made several exports today. Try again tomorrow.", 429
        )
    body = render(user)
    export = DataExport(
        user=user,
        status=ExportStatus.READY,
        created_at=now,
        expires_at=now + timedelta(hours=settings.PRIVACY_EXPORT_KEEP_HOURS),
        size_bytes=len(body),
    )
    export.object_key = f"exports/{user.pk}/{export.pk}.json"
    get_storage().write(export.object_key, body, content_type="application/json")
    with transaction.atomic():
        export.save()
        log_action(
            actor=user,
            action="privacy.export_created",
            obj=export,
            after={"size_bytes": export.size_bytes, "expires_at": export.expires_at},
            request=request,
        )
    return export


def download_url(export: DataExport, *, request=None, now=None) -> str:
    now = now or timezone.now()
    if export.status != ExportStatus.READY or export.expires_at <= now:
        raise ExportError("export_expired", "This export has expired. Make a new one.", 410)
    log_action(actor=export.user, action="privacy.export_link", obj=export, request=request)
    return get_storage().signed_read_url(
        export.object_key,
        expires=timedelta(seconds=settings.PRIVACY_EXPORT_URL_SECONDS),
        download_name=f"barterly-data-{export.created_at:%Y%m%d}.json",
        attachment=True,
    )


def expire_due(now) -> int:
    """Delete export files past their time. Returns how many."""
    storage = get_storage()
    done = 0
    for export in DataExport.objects.filter(status=ExportStatus.READY, expires_at__lte=now):
        storage.delete(export.object_key)
        export.status = ExportStatus.EXPIRED
        export.save(update_fields=["status"])
        done += 1
    return done
