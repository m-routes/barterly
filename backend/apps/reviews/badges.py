"""Reputation badges from rules in settings.REPUTATION_BADGES, so they can change
without code. Each rule:

    {"key": "top_volunteer", "label": "Top Volunteer", "side": "talent" | "host" | "any",
     "all": [{"metric": "completed_volunteer_gigs", "min": 3},
             {"metric": "no_shows", "max": 0}, ...]}

Every condition must hold. A metric that's unknown (None, like a rating with no
reviews yet) fails a condition. check_rules() runs at startup: an unknown metric or a
malformed rule stops the app rather than quietly never awarding a badge.
"""

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

METRICS = frozenset(
    {
        "review_count",
        "rating_average",
        "completed",
        "completed_volunteer_gigs",
        "completed_content_gigs",
        "clean_gigs",
        "no_shows",
        "late_cancellations",
        "disputes",
        "completion_rate",
        "id_verified",
        "instagram_linked",
    }
)
SIDES = frozenset({"talent", "host", "any"})


def check_rules(rules=None) -> None:
    rules = settings.REPUTATION_BADGES if rules is None else rules
    keys = set()
    for rule in rules:
        where = f"REPUTATION_BADGES[{rule.get('key', '?')}]"
        if not rule.get("key") or not rule.get("label"):
            raise ImproperlyConfigured(f"{where}: a badge needs a key and a label.")
        if rule["key"] in keys:
            raise ImproperlyConfigured(f"{where}: the key is used twice.")
        keys.add(rule["key"])
        if rule.get("side") not in SIDES:
            raise ImproperlyConfigured(f"{where}: side must be talent, host or any.")
        conditions = rule.get("all") or []
        if not conditions:
            raise ImproperlyConfigured(f"{where}: give at least one condition.")
        for c in conditions:
            if c.get("metric") not in METRICS:
                raise ImproperlyConfigured(f"{where}: unknown metric {c.get('metric')!r}.")
            if not ({"min", "max"} & set(c)) or set(c) - {"metric", "min", "max"}:
                raise ImproperlyConfigured(f"{where}: a condition has min and/or max only.")


def holds(condition: dict, metrics: dict) -> bool:
    value = metrics.get(condition["metric"])
    if value is None:
        return False
    if "min" in condition and value < condition["min"]:
        return False
    return not ("max" in condition and value > condition["max"])


def award(side: str, metrics: dict, rules=None) -> list[dict]:
    """The badges these metrics earn on this side, as {key, label}."""
    rules = settings.REPUTATION_BADGES if rules is None else rules
    return [
        {"key": rule["key"], "label": rule["label"]}
        for rule in rules
        if rule["side"] in (side, "any") and all(holds(c, metrics) for c in rule["all"])
    ]
