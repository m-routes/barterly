import pytest
from django.core.exceptions import ValidationError

from apps.verification.validators import (
    distance_m,
    gstin_matches_pan,
    last_four,
    mask,
    normalize_gstin,
    normalize_pan,
    validate_in_india,
)


@pytest.mark.parametrize("pan", ["ABCPE1234F", " abcpe1234f ", "AAACB1234Z"])
def test_valid_pans_are_normalized(pan):
    assert normalize_pan(pan) == pan.strip().upper()


@pytest.mark.parametrize("pan", ["", "ABCPE1234", "ABCXE1234F", "12345ABCDE", "ABCPE12345"])
def test_invalid_pans_are_rejected(pan):
    with pytest.raises(ValidationError):
        normalize_pan(pan)


def test_gstin_format_and_pan_match():
    gstin = normalize_gstin("27abcpe1234f1z5")
    assert gstin == "27ABCPE1234F1Z5"
    assert gstin_matches_pan(gstin, "ABCPE1234F")
    assert not gstin_matches_pan(gstin, "ZZZPE1234F")
    with pytest.raises(ValidationError):
        normalize_gstin("27ABCPE1234F1X5")


def test_only_the_last_four_are_kept_and_masked_for_display():
    assert last_four("ABCPE1234F") == "234F"
    assert mask("234F", 10) == "XXXXXX234F"
    assert mask("", 10) == ""


def test_locations_outside_india_are_rejected():
    validate_in_india(32.24, 77.19)
    with pytest.raises(ValidationError):
        validate_in_india(51.5, -0.12)


def test_distance():
    assert distance_m(32.0, 77.0, 32.0, 77.0) == 0
    # 0.01 degree of latitude is about 1.11 km.
    assert 1100 < distance_m(32.0, 77.0, 32.01, 77.0) < 1125
