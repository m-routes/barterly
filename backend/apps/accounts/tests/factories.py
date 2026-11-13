import factory

from apps.accounts.models import Role, User


class UserFactory(factory.django.DjangoModelFactory):
    """Users with valid, unique Indian mobile numbers (+9198765xxxxx)."""

    class Meta:
        model = User
        django_get_or_create = ("phone",)

    phone = factory.Sequence(lambda n: f"+9198765{n:05d}")
    role = Role.TALENT
    password = factory.django.Password("test-password-123")


class VendorFactory(UserFactory):
    role = Role.VENDOR


class TalentFactory(UserFactory):
    role = Role.TALENT


class AdminUserFactory(UserFactory):
    role = Role.ADMIN
    is_staff = True
