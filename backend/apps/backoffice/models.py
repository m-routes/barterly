from django.db import models


class Backoffice(models.Model):
    """No table: a home for the back-office permissions that aren't about one model.

    Django creates these permissions after migrate; roles.py groups them into roles.
    """

    class Meta:
        managed = False
        default_permissions = ()
        permissions = [
            ("review_verification", "Can decide verification cases"),
            ("review_gigs", "Can approve gigs or send them back"),
            ("view_audit_log", "Can read the audit log"),
            ("manage_admin_roles", "Can give staff their admin roles"),
        ]

    def __str__(self) -> str:
        return "Back office"
