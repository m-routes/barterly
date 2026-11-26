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
    """Staff with no back-office role (sees what a stranger sees) unless given roles:
    AdminUserFactory(roles=["ops"])."""

    role = Role.ADMIN
    is_staff = True

    @factory.post_generation
    def roles(self, create, extracted, **kwargs):
        if not (create and extracted):
            return
        from django.contrib.auth.models import Group

        from apps.backoffice.roles import sync_roles

        if Group.objects.filter(name__in=extracted).count() != len(set(extracted)):
            sync_roles()
        self.groups.add(*Group.objects.filter(name__in=extracted))
        # has_perm caches per instance.
        for cache in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
            self.__dict__.pop(cache, None)
