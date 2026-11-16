"""The real renderer. Needs Pango (the API image and CI install it); skipped where it's
missing, e.g. a laptop without it, except in CI (REQUIRE_WEASYPRINT=1), where it must run."""

import os

import pytest

from apps.agreements import pdf
from apps.agreements.tests.helpers import awaiting
from apps.agreements.tests.test_agreements import booking


def _weasyprint_available() -> bool:
    try:
        import weasyprint  # noqa: F401
    except OSError:
        if os.environ.get("REQUIRE_WEASYPRINT"):
            raise
        return False
    return True


pytestmark = [
    pytest.mark.django_db,
    pytest.mark.skipif(not _weasyprint_available(), reason="Pango isn't installed here"),
]


def test_draws_up_a_real_pdf():
    version = awaiting(booking())
    data = pdf.WeasyPrintRenderer().render(pdf.render_html(version))
    assert data.startswith(b"%PDF-") and len(data) > 5_000
