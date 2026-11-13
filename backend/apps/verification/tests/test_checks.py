import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.media.models import MediaStatus
from apps.media.policy import Kind
from apps.profiles.tests.factories import TalentProfileFactory, VendorProfileFactory
from apps.verification.constants import CaseStatus, DocumentType
from apps.verification.services import checks
from apps.verification.services.cases import Decision, InvalidTransition, decide
from apps.verification.tests.factories import PIN, MediaFileFactory

pytestmark = pytest.mark.django_db


def geo(media, metres_north=20):
    return checks.GeoPhoto(
        media_id=str(media.pk),
        latitude=PIN["latitude"] + metres_north / 111_000,
        longitude=PIN["longitude"],
    )


@pytest.fixture
def vendor():
    return VendorProfileFactory(address="Old Manali Road, Manali 175131").user


class TestBusiness:
    def test_stores_only_last_four_and_checks_gstin_holds_the_pan(self, vendor):
        case = checks.submit_business(vendor, pan="abcpe1234f", gstin="27ABCPE1234F1Z5")
        assert case.status == CaseStatus.SUBMITTED
        assert case.details["pan_last_four"] == "234F"
        assert case.details["gstin_last_four"] == "F1Z5"
        docs = {d.document_type: d.masked_value for d in case.documents.all()}
        assert docs == {DocumentType.PAN: "234F", DocumentType.GSTIN: "F1Z5"}
        assert "ABCPE1234F" not in str(case.details)

    def test_gstin_from_another_pan_is_refused(self, vendor):
        with pytest.raises(ValidationError):
            checks.submit_business(vendor, pan="ZZZPE1234F", gstin="27ABCPE1234F1Z5")

    def test_profile_gstin_is_used_when_none_is_sent(self, vendor):
        vendor.vendor_profile.gstin = "27ABCPE1234F1Z5"
        vendor.vendor_profile.save()
        case = checks.submit_business(vendor, pan="ABCPE1234F")
        assert case.documents.filter(document_type=DocumentType.GSTIN).exists()

    def test_gst_is_optional(self, vendor):
        case = checks.submit_business(vendor, pan="ABCPE1234F")
        assert list(case.documents.values_list("document_type", flat=True)) == [DocumentType.PAN]

    def test_cannot_resubmit_while_approved(self, vendor):
        case = checks.submit_business(vendor, pan="ABCPE1234F")
        decide(case.pk, Decision.APPROVE, reviewer=AdminUserFactory())
        with pytest.raises(InvalidTransition):
            checks.submit_business(vendor, pan="ABCPE1234F")


class TestProperty:
    def photos(self, user, n=3, **kwargs):
        return [MediaFileFactory(owner=user, **kwargs) for _ in range(n)]

    def test_pin_and_nearby_photos_are_recorded(self, vendor):
        photos = self.photos(vendor)
        case = checks.submit_property(
            vendor, **PIN, pin_confirmed=True, photos=[geo(p) for p in photos]
        )
        assert case.status == CaseStatus.SUBMITTED
        assert case.subject_type == "property"
        assert case.subject_id == str(vendor.vendor_profile.pk)
        assert case.details["pin"] == PIN
        assert case.details["address"] == "Old Manali Road, Manali 175131"
        assert case.documents.filter(document_type=DocumentType.PROPERTY_PHOTO).count() == 3
        assert case.documents.first().metadata["distance_m"] == 20

    def test_needs_address_confirmation_and_enough_photos(self, vendor):
        photos = [geo(p) for p in self.photos(vendor)]
        with pytest.raises(ValidationError, match="Confirm"):
            checks.submit_property(vendor, **PIN, pin_confirmed=False, photos=photos)
        with pytest.raises(ValidationError, match="at least 3"):
            checks.submit_property(vendor, **PIN, pin_confirmed=True, photos=photos[:2])
        no_address = VendorProfileFactory(address="").user
        with pytest.raises(ValidationError, match="address"):
            checks.submit_property(no_address, **PIN, pin_confirmed=True, photos=photos)

    def test_photos_far_from_the_pin_are_refused(self, vendor):
        photos = self.photos(vendor)
        far = [geo(photos[0]), geo(photos[1]), geo(photos[2], metres_north=2000)]
        with pytest.raises(ValidationError, match="within 500 m"):
            checks.submit_property(vendor, **PIN, pin_confirmed=True, photos=far)

    def test_pin_outside_india_is_refused(self, vendor):
        photos = [geo(p) for p in self.photos(vendor)]
        with pytest.raises(ValidationError):
            checks.submit_property(
                vendor, latitude=0.0, longitude=0.0, pin_confirmed=True, photos=photos
            )

    @pytest.mark.parametrize(
        "make",
        [
            lambda v: MediaFileFactory(),  # someone else's
            lambda v: MediaFileFactory(owner=v, kind=Kind.DOCUMENT),
            lambda v: MediaFileFactory(owner=v, status=MediaStatus.QUARANTINED),
        ],
        ids=["not-mine", "not-a-photo", "quarantined"],
    )
    def test_only_my_usable_photos(self, vendor, make):
        photos = [*self.photos(vendor, n=2), make(vendor)]
        with pytest.raises(ValidationError, match="No usable photo"):
            checks.submit_property(
                vendor, **PIN, pin_confirmed=True, photos=[geo(p) for p in photos]
            )


class TestTalentChecks:
    def test_social_uses_the_profile_handle_and_keeps_its_code(self):
        talent = TalentProfileFactory(instagram_handle="Wall.Painter").user
        case = checks.submit_social(talent)
        assert case.subject_type == "social_account"
        assert case.subject_id == "instagram:wall.painter"
        code = case.details["bio_code"]
        assert code.startswith("BARTERLY-")
        assert checks.submit_social(talent).details["bio_code"] == code

    def test_social_needs_a_handle(self):
        talent = TalentProfileFactory(instagram_handle="").user
        with pytest.raises(ValidationError):
            checks.submit_social(talent)

    def test_certificates_are_my_documents(self):
        talent = TalentFactory()
        doc = MediaFileFactory(owner=talent, kind=Kind.DOCUMENT, content_type="application/pdf")
        case = checks.submit_certificates(
            talent, certificates=[checks.Certificate(media_id=str(doc.pk), title="Yoga RYT-200")]
        )
        assert case.documents.get().media == doc
        assert case.details["titles"] == ["Yoga RYT-200"]

    def test_reference_is_normalized_and_not_my_own_number(self):
        talent = TalentFactory()
        case = checks.submit_reference(
            talent, name=" Asha ", phone="98111 22233", relationship="Hostel manager"
        )
        assert case.details == {
            "name": "Asha",
            "phone": "+919811122233",
            "relationship": "Hostel manager",
        }
        with pytest.raises(ValidationError):
            checks.submit_reference(talent, name="Me", phone=talent.phone, relationship="Self")

    def test_vendor_checks_are_not_for_talent(self):
        from apps.verification.services.cases import CheckNotAvailable

        talent = TalentFactory()
        with pytest.raises(CheckNotAvailable):
            checks.submit_business(talent, pan="ABCPE1234F")


def test_vendor_without_profile_can_still_submit_pan():
    case = checks.submit_business(VendorFactory(), pan="ABCPE1234F")
    assert case.details["business_name"] == ""
