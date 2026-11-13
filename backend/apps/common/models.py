"""Base models and the audit log shared by every app."""

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Adds created_at and updated_at, maintained by the database layer."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def delete(self):
        """Soft-delete every row in the queryset. Returns the number of rows marked."""
        return self.update(deleted_at=timezone.now())

    def hard_delete(self):
        return super().delete()

    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Default manager: hides soft-deleted rows."""

    def get_queryset(self):
        return super().get_queryset().filter(deleted_at__isnull=True)


class AllObjectsManager(models.Manager.from_queryset(SoftDeleteQuerySet)):
    """Includes soft-deleted rows. Use for admin tooling and restores."""


class SoftDeleteModel(models.Model):
    """Rows are marked deleted instead of removed.

    `objects` excludes deleted rows; `all_objects` includes them. `delete()` marks the
    row, `hard_delete()` removes it, `restore()` brings it back. Related-object access
    (e.g. `profile.user`) goes through Django's base manager and still sees deleted rows.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True, editable=False)

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def delete(self, using=None, keep_parents=False):
        self.deleted_at = timezone.now()
        self.save(using=using, update_fields=["deleted_at"])
        return 1, {self._meta.label: 1}

    def hard_delete(self, using=None, keep_parents=False):
        return super().delete(using=using, keep_parents=keep_parents)

    def restore(self) -> None:
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise TypeError("Audit log entries are append-only")

    def delete(self):
        raise TypeError("Audit log entries are append-only")


class AuditLog(models.Model):
    """Append-only record of money and status changes. Write it with log_action()."""

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        # Users with audit history must be deactivated, never hard-deleted.
        on_delete=models.PROTECT,
        related_name="audit_entries",
        help_text="Who made the change. Empty for system actions.",
    )
    action = models.CharField(max_length=100, help_text="Dotted verb, e.g. 'user.role_changed'.")
    object_type = models.CharField(max_length=100, help_text="app_label.model of the target.")
    object_id = models.CharField(max_length=64)
    before = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    after = models.JSONField(null=True, blank=True, encoder=DjangoJSONEncoder)
    ip = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=128, blank=True)
    created_at = models.DateTimeField(default=timezone.now, db_index=True, editable=False)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["object_type", "object_id"], name="audit_object_idx"),
            models.Index(fields=["actor", "created_at"], name="audit_actor_idx"),
            models.Index(fields=["action", "created_at"], name="audit_action_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.action} {self.object_type}:{self.object_id}"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise TypeError("Audit log entries are append-only")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise TypeError("Audit log entries are append-only")
