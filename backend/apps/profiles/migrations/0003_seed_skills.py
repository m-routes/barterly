"""Starter skill list. Admins curate it from here (Django admin -> Skills)."""

from django.db import migrations
from django.utils.text import slugify

SKILLS = [
    "Front desk", "Housekeeping", "Hostel management", "Bartending", "Barista",
    "Cooking", "Baking", "Gardening", "Farming", "Carpentry", "Painting", "Mural art",
    "Interior styling", "Photography", "Videography", "Video editing", "Drone filming",
    "Social media", "Content writing", "Graphic design", "Web development",
    "Marketing", "Yoga", "Meditation", "Fitness training", "Music", "DJing",
    "Event hosting", "Teaching English", "Language exchange", "Tour guiding",
    "Trekking", "Surfing", "Scuba diving", "First aid", "Driving",
]  # fmt: skip


def seed(apps, schema_editor):
    Skill = apps.get_model("profiles", "Skill")
    for name in SKILLS:
        Skill.objects.get_or_create(slug=slugify(name), defaults={"name": name})


def unseed(apps, schema_editor):
    Skill = apps.get_model("profiles", "Skill")
    # Leave any seeded skill that a profile already uses.
    Skill.objects.filter(
        slug__in=[slugify(n) for n in SKILLS], talent_profiles__isnull=True
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("profiles", "0002_reshape_profiles")]

    operations = [migrations.RunPython(seed, unseed)]
