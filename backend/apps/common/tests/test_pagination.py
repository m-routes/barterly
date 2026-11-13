import pytest
from rest_framework import generics, serializers
from rest_framework.permissions import AllowAny
from rest_framework.test import APIRequestFactory

from apps.accounts.models import User
from apps.accounts.tests.factories import TalentFactory
from apps.common.pagination import DefaultPagination

factory = APIRequestFactory()


class PhoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["phone"]


class UserList(generics.ListAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    serializer_class = PhoneSerializer
    queryset = User.objects.order_by("phone")


def get(query=""):
    return UserList.as_view()(factory.get(f"/api/users/{query}")).data


def test_default_pagination_is_configured(settings):
    assert settings.REST_FRAMEWORK["DEFAULT_PAGINATION_CLASS"].endswith("DefaultPagination")
    assert DefaultPagination.page_size == 20
    assert DefaultPagination.max_page_size == 100


@pytest.mark.django_db
def test_page_shape_and_default_size():
    TalentFactory.create_batch(25)
    data = get()
    assert set(data) == {"count", "next", "previous", "results"}
    assert data["count"] == 25
    assert len(data["results"]) == 20
    assert data["previous"] is None
    assert "page=2" in data["next"]


@pytest.mark.django_db
def test_page_size_param_is_capped(monkeypatch):
    monkeypatch.setattr(DefaultPagination, "max_page_size", 3)
    TalentFactory.create_batch(5)
    assert len(get("?page_size=2")["results"]) == 2
    assert len(get("?page_size=500")["results"]) == 3
