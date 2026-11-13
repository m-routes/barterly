import pytest
from django.core.exceptions import ValidationError

from apps.accounts.services.phone import normalize_phone


@pytest.mark.parametrize(
    "raw",
    ["9876543210", "+91 98765 43210", "098765-43210", "+919876543210", " 98765 43210 "],
)
def test_indian_numbers_normalise_to_e164(raw):
    assert normalize_phone(raw) == "+919876543210"


def test_other_countries_need_a_country_code():
    assert normalize_phone("+44 20 7946 0958") == "+442079460958"


@pytest.mark.parametrize("raw", ["12345", "abc", "+91 00000 00000", "+999 123"])
def test_invalid_numbers_are_rejected(raw):
    with pytest.raises(ValidationError) as info:
        normalize_phone(raw)
    assert info.value.code == "invalid"


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_blank_is_required(raw):
    with pytest.raises(ValidationError) as info:
        normalize_phone(raw)
    assert info.value.code == "required"
