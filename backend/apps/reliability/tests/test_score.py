"""The pure formula (apps.reliability.score). No database."""

import pytest

from apps.reliability.score import NEUTRAL, Inputs, score


def test_everyone_starts_neutral_and_new():
    result = score(Inputs())
    assert (result.score, result.level, result.version) == (NEUTRAL, "new", "v1")
    assert sum(result.breakdown.values()) == NEUTRAL


def test_completed_bookings_raise_it_up_to_a_cap():
    assert score(Inputs(completed=1)).score == 56
    assert score(Inputs(completed=5)).score == 80
    assert score(Inputs(completed=50)).score == 80  # capped at +30
    assert score(Inputs(completed=1)).level == "fair"
    assert score(Inputs(completed=2)).level == "good"
    assert score(Inputs(completed=5)).level == "excellent"


def test_on_time_replies_raise_it_a_little_and_dont_end_newness():
    assert score(Inputs(on_time_replies=4)).score == 54
    assert score(Inputs(on_time_replies=40)).score == 60  # capped at +10
    assert score(Inputs(on_time_replies=40)).level == "new"


def test_late_cancellations_and_no_shows_lower_it_without_a_cap():
    assert score(Inputs(late_cancellations=1)).score == 40
    assert score(Inputs(last_minute_cancellations=1)).score == 30
    assert score(Inputs(no_shows=1)).score == 25
    assert score(Inputs(no_shows=1)).level == "poor"
    assert score(Inputs(no_shows=3)).score == 0  # never below 0
    assert score(Inputs(late_cancellations=1)).level == "fair"


def test_a_long_record_cant_buy_immunity():
    veteran = Inputs(completed=50, on_time_replies=50, no_shows=1)
    assert score(veteran).score == 65  # 50 + 30 + 10 - 25
    assert score(Inputs(completed=50, on_time_replies=50)).score == 90
    assert score(Inputs(completed=50, on_time_replies=50)).score <= 100


def test_the_breakdown_explains_the_score():
    result = score(Inputs(completed=2, on_time_replies=3, late_cancellations=1))
    assert result.breakdown == {
        "neutral": 50,
        "completed": 12,
        "on_time_replies": 3,
        "late_cancellations": -10,
        "last_minute_cancellations": 0,
        "no_shows": 0,
    }
    assert result.score == 55


def test_it_is_pure_and_deterministic():
    inputs = Inputs(completed=3, no_shows=1)
    assert score(inputs) == score(inputs)


@pytest.mark.parametrize("bad", [-1, 1.5, True, "2", None])
def test_inputs_must_be_whole_numbers(bad):
    with pytest.raises(ValueError, match="whole number"):
        Inputs(completed=bad)
