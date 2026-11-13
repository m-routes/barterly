import pytest

from apps.accounts.auth.verifiers import VerifiedIdentity
from apps.accounts.models import Role
from apps.accounts.services.auth import RoleAlreadySet, choose_role, sign_in
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_sign_in_returns_a_token_pair_for_the_user():
    result = sign_in(VerifiedIdentity(phone="+919800000001", provider="fake", provider_uid="u1"))
    assert result.created is True
    assert result.access and result.refresh and result.access != result.refresh


def test_choose_role_rejects_admin_and_already_set_roles():
    user = UserFactory(role="")
    with pytest.raises(ValueError):
        choose_role(user, Role.ADMIN)
    choose_role(user, Role.TALENT)
    assert user.role == Role.TALENT
    with pytest.raises(RoleAlreadySet):
        choose_role(user, Role.VENDOR)
