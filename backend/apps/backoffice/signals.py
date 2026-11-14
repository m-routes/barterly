"""Every change made in the Django admin also lands in the audit log."""

from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.common.services.audit import log_action

ADMIN_ACTIONS = {ADDITION: "admin.added", CHANGE: "admin.changed", DELETION: "admin.deleted"}


@receiver(post_save, sender=LogEntry)
def audit_admin_entry(sender, instance: LogEntry, created: bool, **kwargs) -> None:
    """Django writes a LogEntry for each add, change and delete in the admin; copy it
    into the append-only AuditLog with what changed."""
    if not created or instance.content_type_id is None:
        return
    content_type = instance.content_type
    log_action(
        actor=instance.user,
        action=ADMIN_ACTIONS.get(instance.action_flag, "admin.other"),
        object_type=f"{content_type.app_label}.{content_type.model}",
        object_id=instance.object_id or "-",
        after={"summary": instance.get_change_message(), "object": instance.object_repr},
    )


def sync_roles_after_migrate(sender, **kwargs) -> None:
    from apps.backoffice.roles import sync_roles

    sync_roles()
