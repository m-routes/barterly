"""Back-office roles, each with only the permissions its work needs.

A role is a Django auth Group named after it. sync_roles() (run after every migrate)
makes each group's permissions exactly the ones listed here, so the list in this file
is the source of truth: editing a group in the admin is undone on the next deploy.

Give someone a role with `manage.py grant_admin_role <phone> <role>` (audited).
"""

from django.contrib.auth.models import Group, Permission
from django.db import models


class AdminRole(models.TextChoices):
    SUPER_ADMIN = "super_admin", "Super admin"
    OPS = "ops", "Operations"
    TRUST = "trust", "Trust and safety"
    FINANCE = "finance", "Finance"
    SUPPORT = "support", "Support"


# Read-only access to what support and ops look up when helping someone.
LOOKUP = [
    "accounts.view_user",
    "profiles.view_talentprofile",
    "profiles.view_vendorprofile",
    "properties.view_property",
    "properties.view_propertyphoto",
    "gigs.view_gig",
    "applications.view_application",
]
VERIFICATION_READ = [
    "verification.view_verificationcase",
    "verification.view_verificationdocument",
    "verification.view_badge",
]

PERMISSIONS: dict[str, list[str]] = {
    # Everything below, plus staff and role management.
    AdminRole.SUPER_ADMIN: [],  # filled in below
    # Runs the marketplace: approves gigs, looks up accounts.
    AdminRole.OPS: [
        *LOOKUP,
        "backoffice.review_gigs",
        "backoffice.view_audit_log",
    ],
    # Verification and fraud: decides cases, sees badges and provider events.
    AdminRole.TRUST: [
        *LOOKUP,
        *VERIFICATION_READ,
        "verification.view_kycwebhookevent",
        "backoffice.review_verification",
        "backoffice.view_audit_log",
    ],
    # Money: reads gigs (stipends) and the audit trail of money changes.
    AdminRole.FINANCE: [
        "accounts.view_user",
        "gigs.view_gig",
        "applications.view_application",
        "backoffice.view_audit_log",
    ],
    # Helps people: looks things up, changes nothing.
    AdminRole.SUPPORT: [*LOOKUP, *VERIFICATION_READ],
}
PERMISSIONS[AdminRole.SUPER_ADMIN] = sorted(
    {p for role, perms in PERMISSIONS.items() for p in perms}
    | {
        "accounts.change_user",
        "auth.view_group",
        "backoffice.manage_admin_roles",
    }
)


def _permission(dotted: str) -> Permission:
    app_label, codename = dotted.split(".", 1)
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def sync_roles() -> None:
    """Create the role groups and set their permissions to exactly PERMISSIONS."""
    for role, dotted in PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role)
        group.permissions.set([_permission(p) for p in dotted])


def roles_of(user) -> list[str]:
    names = set(user.groups.values_list("name", flat=True))
    return [r for r in AdminRole.values if r in names]
