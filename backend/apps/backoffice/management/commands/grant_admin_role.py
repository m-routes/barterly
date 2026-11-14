from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Role, User
from apps.backoffice.roles import AdminRole, roles_of, sync_roles
from apps.common.services.audit import log_action


class Command(BaseCommand):
    help = (
        "Give a staff member a back-office role (super_admin, ops, trust, finance, support), "
        "or take it away with --remove. Makes them an admin who can sign in to /admin/. "
        "Audit-logged."
    )

    def add_arguments(self, parser):
        parser.add_argument("phone", help="E.164, e.g. +919812345678")
        parser.add_argument("role", choices=AdminRole.values)
        parser.add_argument("--remove", action="store_true", help="Take the role away.")

    def handle(self, *args, phone, role, remove, **options):
        sync_roles()
        try:
            user = User.objects.get(phone=phone)
        except User.DoesNotExist as exc:
            raise CommandError(f"No user with phone {phone}.") from exc
        if not remove and user.role not in (Role.ADMIN, ""):
            raise CommandError(
                f"{phone} is a {user.role} account. Use a separate account for admin work."
            )
        with transaction.atomic():
            before = {"roles": roles_of(user), "role": user.role, "is_staff": user.is_staff}
            group = Group.objects.get(name=role)
            if remove:
                user.groups.remove(group)
            else:
                user.groups.add(group)
                user.role = Role.ADMIN
                user.is_staff = True
                user.save(update_fields=["role", "is_staff", "updated_at"])
            log_action(
                actor=None,
                action="user.admin_role_removed" if remove else "user.admin_role_granted",
                obj=user,
                before=before,
                after={"roles": roles_of(user), "role": user.role, "is_staff": user.is_staff},
            )
        verb = "Removed" if remove else "Granted"
        self.stdout.write(
            f"{verb} {role} for {phone}. Roles now: {', '.join(roles_of(user)) or 'none'}."
        )
