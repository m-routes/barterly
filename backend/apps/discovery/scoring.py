"""The gig fit score: 0-100 from weighted components, as a pure function.

No database access and no settings lookups: callers pass the facts and the weights
(settings.DISCOVERY_FIT_WEIGHTS). Every component is a value from 0 to 1. Missing data
gives the neutral value (0.5), never zero, so a new talent or a new host isn't punished
for having no history yet. The breakdown says which components were neutral so the UI
can explain the score.
"""

from dataclasses import dataclass
from datetime import date

NEUTRAL = 0.5
COMPONENTS = ("skill_match", "reliability", "ratings", "audience_quality", "distance_availability")


@dataclass(frozen=True)
class TalentFacts:
    skills: frozenset[str] = frozenset()
    reliability: float | None = None  # 0-1: show-up and completion rate (Phase 3)
    rating: float | None = None  # 1-5 average from hosts (Phase 3)
    audience_quality: float | None = None  # 0-1: engagement quality, not follower count
    available_from: date | None = None
    available_to: date | None = None


@dataclass(frozen=True)
class GigFacts:
    skills: frozenset[str] = frozenset()
    start_date: date | None = None
    end_date: date | None = None  # end date, or start plus duration
    distance_km: float | None = None  # from the searcher's point to the approximate location


@dataclass(frozen=True)
class Component:
    value: float  # 0-1
    weight: float
    points: float  # value * weight
    neutral: bool  # True when data was missing and the neutral value was used
    reason: str

    def as_dict(self) -> dict:
        return {
            "value": round(self.value, 3),
            "weight": self.weight,
            "points": round(self.points, 1),
            "neutral": self.neutral,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class FitResult:
    score: int
    components: dict[str, Component]

    def breakdown(self) -> dict:
        return {name: c.as_dict() for name, c in self.components.items()}


def fit_score(
    talent: TalentFacts,
    gig: GigFacts,
    *,
    weights: dict[str, float],
    distance_zero_km: float = 300,
) -> FitResult:
    """Score how well a gig fits a talent, from 0 to 100."""
    missing = set(COMPONENTS) - set(weights)
    if missing:
        raise ValueError(f"Weights missing for: {', '.join(sorted(missing))}")
    total_weight = sum(weights[name] for name in COMPONENTS)
    if total_weight <= 0:
        raise ValueError("Weights must add up to more than zero.")

    values = {
        "skill_match": _skill_match(talent, gig),
        "reliability": _known(talent.reliability, "Show-up and completion record."),
        "ratings": _rating(talent.rating),
        "audience_quality": _known(talent.audience_quality, "Audience engagement quality."),
        "distance_availability": _distance_availability(talent, gig, distance_zero_km),
    }
    components = {
        name: Component(
            value=value,
            weight=weights[name],
            points=value * weights[name] * 100 / total_weight,
            neutral=neutral,
            reason=reason,
        )
        for name, (value, neutral, reason) in values.items()
    }
    score = round(sum(c.points for c in components.values()))
    return FitResult(score=max(0, min(100, score)), components=components)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _known(value: float | None, reason: str) -> tuple[float, bool, str]:
    if value is None:
        return NEUTRAL, True, "No history yet."
    return _clamp(value), False, reason


def _rating(rating: float | None) -> tuple[float, bool, str]:
    if rating is None:
        return NEUTRAL, True, "No ratings yet."
    return _clamp((rating - 1) / 4), False, f"Rated {rating:.1f} of 5 by hosts."


def _skill_match(talent: TalentFacts, gig: GigFacts) -> tuple[float, bool, str]:
    if not gig.skills:
        return NEUTRAL, True, "The gig lists no skills."
    if not talent.skills:
        return NEUTRAL, True, "Your profile lists no skills."
    matched = len(talent.skills & gig.skills)
    return matched / len(gig.skills), False, f"{matched} of {len(gig.skills)} skills match."


def _distance_availability(
    talent: TalentFacts, gig: GigFacts, distance_zero_km: float
) -> tuple[float, bool, str]:
    parts, reasons = [], []
    if gig.distance_km is not None:
        parts.append(_clamp(1 - gig.distance_km / distance_zero_km))
        reasons.append(f"About {gig.distance_km:.0f} km away.")
    availability = _availability(talent, gig)
    if availability is not None:
        parts.append(availability)
        reasons.append(f"You're free for {availability:.0%} of it.")
    if not parts:
        return NEUTRAL, True, "No location or dates to compare."
    # A known half and a missing half: the missing one counts as neutral.
    while len(parts) < 2:
        parts.append(NEUTRAL)
    return sum(parts) / 2, False, " ".join(reasons)


def _availability(talent: TalentFacts, gig: GigFacts) -> float | None:
    if not (talent.available_from and talent.available_to and gig.start_date and gig.end_date):
        return None
    length = (gig.end_date - gig.start_date).days
    if length <= 0:
        return None
    overlap_start = max(talent.available_from, gig.start_date)
    overlap_end = min(talent.available_to, gig.end_date)
    return _clamp((overlap_end - overlap_start).days / length)
