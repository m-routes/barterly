from apps.agreements import services
from apps.agreements.models import AgreementVersion, VersionStatus


def awaiting(booking) -> AgreementVersion:
    return AgreementVersion.objects.get(agreement__booking=booking, status=VersionStatus.AWAITING)


def sign(version, user, **kwargs):
    version.refresh_from_db()
    return services.sign(
        version.pk,
        user=user,
        consent=kwargs.pop("consent", True),
        document_sha256=kwargs.pop("document_sha256", version.pdf_sha256),
        **kwargs,
    )


def sign_both(booking) -> AgreementVersion:
    """Both sides sign the version waiting for signatures (fake e-sign provider)."""
    version = awaiting(booking)
    sign(version, booking.vendor)
    sign(version, booking.talent)
    version.refresh_from_db()
    return version
