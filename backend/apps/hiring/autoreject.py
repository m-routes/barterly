"""Auto-reject rules: a vendor's requirements, checked the moment someone applies.

Unlike the hard eligibility checks (which stop an application being sent at all),
these let the application in and then reject it at once, telling the applicant exactly
which requirement they missed. Rules live on the gig (Gig.auto_reject_rules):

    [{"type": "language", "languages": ["hi", "ta"]},
     {"type": "skill", "skills": ["photography"]},
     {"type": "min_followers", "value": 5000},
     {"type": "min_stay_days", "value": 30}]
"""

from django.core.exceptions import ValidationError

from apps.profiles.constants import LANGUAGES

MAX_RULES = 10
RULE_TYPES = ("language", "skill", "min_followers", "min_stay_days")


def clean_rules(rules) -> list[dict]:
    """Validate and normalise a rule list, or raise ValidationError."""
    from apps.profiles.models import Skill

    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise ValidationError(f"Send a list of at most {MAX_RULES} rules.")
    cleaned = []
    for i, rule in enumerate(rules, start=1):
        kind = rule.get("type") if isinstance(rule, dict) else None
        if kind not in RULE_TYPES:
            raise ValidationError(f"Rule {i}: type must be one of {', '.join(RULE_TYPES)}.")
        if kind == "language":
            codes = rule.get("languages")
            if not codes or not isinstance(codes, list) or set(codes) - set(LANGUAGES):
                raise ValidationError(f"Rule {i}: list known language codes.")
            cleaned.append({"type": kind, "languages": sorted(set(codes))})
        elif kind == "skill":
            slugs = rule.get("skills")
            if not slugs or not isinstance(slugs, list):
                raise ValidationError(f"Rule {i}: list at least one skill.")
            known = set(Skill.objects.filter(slug__in=slugs).values_list("slug", flat=True))
            if unknown := sorted(set(slugs) - known):
                raise ValidationError(f"Rule {i}: unknown skills {', '.join(unknown)}.")
            cleaned.append({"type": kind, "skills": sorted(set(slugs))})
        else:
            value = rule.get("value")
            if (
                not isinstance(value, int)
                or isinstance(value, bool)
                or not 1 <= value <= 10_000_000
            ):
                raise ValidationError(f"Rule {i}: value must be a positive whole number.")
            cleaned.append({"type": kind, "value": value})
    return cleaned


def failures(application, profile) -> list[str]:
    """Why this application misses the gig's rules, in words for the applicant."""
    messages = []
    for rule in application.gig.auto_reject_rules or []:
        kind = rule["type"]
        if kind == "language":
            if not set(rule["languages"]) & set(profile.languages or []):
                names = ", ".join(LANGUAGES[c] for c in rule["languages"])
                messages.append(
                    f"speaks {names}" if len(rule["languages"]) == 1 else f"speaks one of {names}"
                )
        elif kind == "skill":
            have = set(profile.skills.values_list("slug", flat=True))
            if not set(rule["skills"]) & have:
                messages.append(f"has the skill {' or '.join(rule['skills'])} on their profile")
        elif kind == "min_followers":
            if (profile.instagram_followers or 0) < rule["value"]:
                messages.append(f"has at least {rule['value']:,} Instagram followers")
        elif kind == "min_stay_days":
            stay = (application.proposed_end - application.proposed_start).days
            if stay < rule["value"]:
                messages.append(f"can stay at least {rule['value']} days (you proposed {stay})")
    return messages


def explain(missing: list[str]) -> str:
    return "This host is looking for someone who " + "; and who ".join(missing) + "."
