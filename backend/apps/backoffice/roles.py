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
    "bookings.view_booking",
]
VERIFICATION_READ = [
    "verification.view_verificationcase",
    "verification.view_verificationdocument",
    "verification.view_badge",
]
# Answering support requests: the inbox, people's timelines and the canned replies.
SUPPORT_DESK = [
    "support.handle_tickets",
    "support.view_timeline",
    "support.view_cannedresponse",
    "support.add_cannedresponse",
    "support.change_cannedresponse",
]

PERMISSIONS: dict[str, list[str]] = {
    # Everything below, plus staff and role management.
    AdminRole.SUPER_ADMIN: [],  # filled in below
    # Runs the marketplace: approves gigs, looks up accounts.
    AdminRole.OPS: [
        *LOOKUP,
        "backoffice.review_gigs",
        "backoffice.view_audit_log",
        "bookings.change_booking",
        "flags.toggle_flag",
        "attendance.view_checkin",
        "attendance.review_checkin",
        # The closed beta: invites, onboarding, KPIs, and the support inbox as backup.
        "beta.manage_invites",
        "beta.view_onboarding",
        "beta.view_invitecode",
        "beta.view_inviteredemption",
        "beta.review_safety",
        "beta.view_safetyreview",
        "analytics.view_kpis",
        *SUPPORT_DESK,
    ],
    # Verification, fraud and reviews: decides cases, sees badges and provider events,
    # moderates held and reported reviews.
    AdminRole.TRUST: [
        *LOOKUP,
        *VERIFICATION_READ,
        "verification.view_kycwebhookevent",
        "backoffice.review_verification",
        "backoffice.view_audit_log",
        "bookings.change_booking",
        "media.view_mediafile",
        "flags.toggle_flag",
        "reviews.view_review",
        "reviews.view_reviewreport",
        "reviews.moderate_review",
        # Every dispute and safety report gets the weekly review.
        "beta.review_safety",
        "beta.view_safetyreview",
        "analytics.view_kpis",
        *SUPPORT_DESK,
    ],
    # Money: reads gigs (stipends), the ledger and escrows, and the audit trail of money
    # changes; decides held escrows and runs the kill switch.
    AdminRole.FINANCE: [
        "accounts.view_user",
        "gigs.view_gig",
        "applications.view_application",
        "bookings.view_booking",
        "backoffice.view_audit_log",
        "money.view_account",
        "money.view_ledgertransaction",
        "money.view_ledgerentry",
        "money.view_escrow",
        "money.view_payoutaccount",
        "money.view_deliverablesubmission",
        "money.view_gatewayevent",
        "money.view_reconciliationrun",
        "money.view_escrowcontrol",
        "money.decide_escrow",
        "money.toggle_kill_switch",
        "flags.toggle_flag",
        "money.view_payoutrun",
        "money.view_payout",
        "money.run_payouts",
        "analytics.view_kpis",
    ],
    # Helps people: looks things up and answers requests; changes nothing else.
    AdminRole.SUPPORT: [*LOOKUP, *VERIFICATION_READ, *SUPPORT_DESK, "beta.view_onboarding"],
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
