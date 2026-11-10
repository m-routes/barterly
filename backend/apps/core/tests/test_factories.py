import pytest

from apps.core.tests.factories import UserFactory


@pytest.mark.django_db
def test_user_factory_creates_user_with_usable_password():
    user = UserFactory()
    assert user.pk is not None
    assert user.check_password("test-password-123")
