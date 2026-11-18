"""The three plans (prices are placeholders to set before launch; editable in admin)."""

from django.db import migrations

PLANS = [
    {
        "code": "starter",
        "name": "Starter",
        "description": "One live gig, applicants and agreements.",
        "price_paise": 99900,
        "max_live_gigs": 1,
        "features": {
            "talent_search": False,
            "agreements": True,
            "ai_fit_scores": False,
            "team_roles": False,
        },
        "position": 1,
    },
    {
        "code": "growth",
        "name": "Growth",
        "description": "Talent search, agreements and AI fit scores.",
        "price_paise": 249900,
        "max_live_gigs": 5,
        "features": {
            "talent_search": True,
            "agreements": True,
            "ai_fit_scores": True,
            "team_roles": False,
        },
        "position": 2,
    },
    {
        "code": "pro",
        "name": "Pro",
        "description": "Unlimited live gigs and team roles.",
        "price_paise": 599900,
        "max_live_gigs": None,
        "features": {
            "talent_search": True,
            "agreements": True,
            "ai_fit_scores": True,
            "team_roles": True,
        },
        "position": 3,
    },
]


def seed(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for data in PLANS:
        Plan.objects.update_or_create(code=data["code"], defaults=data)


def unseed(apps, schema_editor):
    apps.get_model("billing", "Plan").objects.filter(
        code__in=[p["code"] for p in PLANS], subscriptions__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("billing", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
