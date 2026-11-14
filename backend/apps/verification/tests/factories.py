import datetime

import factory
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import VendorFactory
from apps.media.models import MediaFile, MediaStatus
from apps.media.policy import Kind
from apps.verification.constants import CaseStatus, CheckType, SubjectType
from apps.verification.models import VerificationCase

# Manali; photos below are a few metres away.
PIN = {"latitude": 32.2432, "longitude": 77.1892}


class MediaFileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = MediaFile

    owner = factory.SubFactory(VendorFactory)
    kind = Kind.PHOTO
    status = MediaStatus.READY
    content_type = "image/jpeg"
    size_bytes = 1024
    object_key = factory.Sequence(lambda n: f"test/{n}.jpg")
    upload_expires_at = factory.LazyFunction(lambda: timezone.now() + datetime.timedelta(hours=1))


class CaseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = VerificationCase

    user = factory.SubFactory(VendorFactory)
    check_type = CheckType.ID_SELFIE
    subject_type = SubjectType.USER
    status = CaseStatus.SUBMITTED


def client_for(user) -> APIClient:
    client = APIClient()
    client.force_authenticate(user)
    return client
