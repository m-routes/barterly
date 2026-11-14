from datetime import date

import pytest

from apps.discovery.scoring import NEUTRAL, GigFacts, TalentFacts, fit_score

WEIGHTS = {
    "skill_match": 30,
    "reliability": 25,
    "ratings": 20,
    "audience_quality": 15,
    "distance_availability": 10,
}


def test_no_data_at_all_is_neutral_not_zero():
    result = fit_score(TalentFacts(), GigFacts(), weights=WEIGHTS)
    assert result.score == 50
    assert all(c.neutral and c.value == NEUTRAL for c in result.components.values())


def test_a_perfect_fit_is_100():
    result = fit_score(
        TalentFacts(
            skills=frozenset({"cooking", "yoga"}),
            reliability=1.0,
            rating=5.0,
            audience_quality=1.0,
            available_from=date(2027, 1, 1),
            available_to=date(2027, 3, 1),
        ),
        GigFacts(
            skills=frozenset({"cooking", "yoga"}),
            start_date=date(2027, 1, 10),
            end_date=date(2027, 2, 10),
            distance_km=0,
        ),
        weights=WEIGHTS,
    )
    assert result.score == 100
    assert not any(c.neutral for c in result.components.values())


def test_breakdown_explains_each_component():
    result = fit_score(
        TalentFacts(skills=frozenset({"cooking"})),
        GigFacts(skills=frozenset({"cooking", "yoga"}), distance_km=150),
        weights=WEIGHTS,
    )
    breakdown = result.breakdown()
    assert breakdown["skill_match"] == {
        "value": 0.5,
        "weight": 30,
        "points": 15.0,
        "neutral": False,
        "reason": "1 of 2 skills match.",
    }
    assert breakdown["reliability"]["neutral"] is True
    # Distance known (halfway to zero), availability unknown (neutral): 0.5.
    assert breakdown["distance_availability"]["value"] == 0.5
    assert "150 km" in breakdown["distance_availability"]["reason"]
    assert result.score == round(sum(c["points"] for c in breakdown.values()))


def test_ratings_scale_from_one_to_five():
    low = fit_score(TalentFacts(rating=1.0), GigFacts(), weights=WEIGHTS).components["ratings"]
    high = fit_score(TalentFacts(rating=4.0), GigFacts(), weights=WEIGHTS).components["ratings"]
    assert low.value == 0 and high.value == 0.75


def test_far_and_partly_available():
    result = fit_score(
        TalentFacts(available_from=date(2027, 1, 1), available_to=date(2027, 1, 16)),
        GigFacts(start_date=date(2027, 1, 1), end_date=date(2027, 1, 31), distance_km=900),
        weights=WEIGHTS,
    )
    component = result.components["distance_availability"]
    assert component.value == pytest.approx((0 + 0.5) / 2)


def test_weights_scale_to_100_and_must_be_complete():
    doubled = {k: v * 2 for k, v in WEIGHTS.items()}
    assert fit_score(TalentFacts(), GigFacts(), weights=doubled).score == 50
    with pytest.raises(ValueError):
        fit_score(TalentFacts(), GigFacts(), weights={"skill_match": 100})
    with pytest.raises(ValueError):
        fit_score(TalentFacts(), GigFacts(), weights=dict.fromkeys(WEIGHTS, 0))


def test_pure_no_database_needed():
    # No django_db mark: this would fail if scoring touched the database.
    assert fit_score(TalentFacts(reliability=0.2), GigFacts(), weights=WEIGHTS).score < 50
