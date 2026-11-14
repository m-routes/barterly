from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.forms import AdminUserCreationForm, UserChangeForm
from django.db import transaction

from apps.accounts.models import User
from apps.accounts.services.users import AUDITED_FIELDS, audit_user_change
from apps.common.services.audit import log_action


class UserCreateForm(AdminUserCreationForm):
    class Meta:
        model = User
        fields = ("phone", "email", "role")


class UserEditForm(UserChangeForm):
    class Meta:
        model = User
        fields = "__all__"


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    form = UserEditForm
    add_form = UserCreateForm
    ordering = ["-created_at"]
    list_display = ["phone", "email", "role", "is_active", "is_staff", "created_at"]
    list_filter = ["role", "is_active", "is_staff", "is_superuser"]
    search_fields = ["phone", "email"]
    readonly_fields = ["id", "last_login", "created_at", "updated_at"]
    fieldsets = (
        (None, {"fields": ("id", "phone", "password")}),
        ("Profile", {"fields": ("email", "role")}),
        (
            "Status and permissions",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Dates", {"fields": ("last_login", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("phone", "email", "role", "usable_password", "password1", "password2"),
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        # Role and status edits made in the admin are audit-logged like any other.
        before = {f: form.initial.get(f) for f in AUDITED_FIELDS if f in form.changed_data}
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            if change:
                audit_user_change(obj, before, actor=request.user, request=request)

    def save_related(self, request, form, formsets, change):
        # Group membership is what gives staff their admin role: audit it too.
        before = sorted(g.name for g in form.initial.get("groups", []) or [])
        super().save_related(request, form, formsets, change)
        after = sorted(form.instance.groups.values_list("name", flat=True))
        if change and before != after:
            log_action(
                actor=request.user,
                action="user.admin_roles_changed",
                obj=form.instance,
                before={"groups": before},
                after={"groups": after},
                request=request,
            )
