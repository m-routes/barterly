"""Custom user: UUID primary key, phone number as the login identifier."""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.services.phone import normalize_phone
from apps.common.models import TimeStampedModel


class Role(models.TextChoices):
    VENDOR = "vendor", "Vendor"
    TALENT = "talent", "Talent"
    ADMIN = "admin", "Admin"


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        # Optional: blank becomes NULL so the conditional unique constraint ignores it.
        email = (email or "").strip()
        return email.lower() or None

    def get_by_natural_key(self, phone):
        try:
            phone = normalize_phone(phone)
        except ValidationError as exc:
            raise self.model.DoesNotExist from exc
        return self.get(phone=phone)

    def _create_user(self, phone, password, **extra_fields):
        try:
            phone = normalize_phone(phone)
        except ValidationError as exc:
            raise ValidationError({"phone": exc.messages}) from exc
        user = self.model(
            phone=phone,
            email=self.normalize_email(extra_fields.pop("email", None)),
            **extra_fields,
        )
        if password:
            user.set_password(password)
        else:
            # Users normally sign in with a phone OTP (Firebase), not a password.
            user.set_unusable_password()
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_user(self, phone, password=None, *, role="", **extra_fields):
        # role "" means "not chosen yet": OTP sign-up creates the user, then the user
        # picks vendor or talent once (POST /api/v1/me/role/).
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(phone, password, role=role, **extra_fields)

    def create_superuser(self, phone, password=None, **extra_fields):
        extra_fields.setdefault("role", Role.ADMIN)
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields["role"] != Role.ADMIN:
            raise ValueError("Superusers must have the admin role.")
        if not extra_fields["is_staff"] or not extra_fields["is_superuser"]:
            raise ValueError("Superusers must have is_staff and is_superuser set.")
        return self._create_user(phone, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(
        max_length=16,
        unique=True,
        help_text="Login identifier, stored in E.164 (e.g. +919876543210).",
    )
    # NULL, not '', for "no email": the conditional unique constraint skips NULLs.
    email = models.EmailField(null=True, blank=True)  # noqa: DJ001
    # "" until the user picks vendor or talent after their first sign-in.
    role = models.CharField(
        max_length=16, choices=Role.choices, blank=True, default="", db_index=True
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Unset instead of deleting accounts. Changes are audit-logged.",
    )
    is_staff = models.BooleanField(default=False, help_text="Can log in to the Django admin.")

    objects = UserManager()

    USERNAME_FIELD = "phone"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=models.Q(email__isnull=False),
                name="accounts_user_email_ci_unique",
                violation_error_message="A user with this email already exists.",
            ),
            models.CheckConstraint(
                condition=models.Q(role__in=[*Role.values, ""]),
                name="accounts_user_role_valid",
            ),
        ]

    def __str__(self) -> str:
        return self.phone

    def clean(self):
        super().clean()
        if self.phone:
            try:
                self.phone = normalize_phone(self.phone)
            except ValidationError as exc:
                raise ValidationError({"phone": exc.messages}) from exc
        self.email = UserManager.normalize_email(self.email)

    @property
    def has_role(self) -> bool:
        return bool(self.role)

    @property
    def is_vendor(self) -> bool:
        return self.role == Role.VENDOR

    @property
    def is_talent(self) -> bool:
        return self.role == Role.TALENT

    @property
    def is_admin_role(self) -> bool:
        return self.role == Role.ADMIN
