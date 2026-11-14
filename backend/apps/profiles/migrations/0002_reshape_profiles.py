"""Profile fields for the profile endpoints; talent skills move from JSON to a table.

Reversible: the reverse copies skills back into the JSON list and language codes back
to names. Unknown language names have no code and are dropped going forward.
"""

import django.db.models.deletion  # noqa: F401
import django.db.models.functions.text
from django.db import migrations, models
from django.utils.text import slugify

import apps.profiles.models
from apps.profiles.constants import LANGUAGES

NAME_TO_CODE = {name.lower(): code for code, name in LANGUAGES.items()}


def skills_and_languages_forward(apps, schema_editor):
    TalentProfile = apps.get_model("profiles", "TalentProfile")
    Skill = apps.get_model("profiles", "Skill")
    for profile in TalentProfile.objects.all():
        for name in profile.legacy_skills or []:
            name = str(name).strip()[:60]
            slug = slugify(name)[:60]
            if not slug:
                continue
            skill = Skill.objects.filter(slug=slug).first() or Skill.objects.create(
                name=name, slug=slug
            )
            profile.skills.add(skill)
        codes = []
        for value in profile.languages or []:
            value = str(value).strip()
            code = value if value in LANGUAGES else NAME_TO_CODE.get(value.lower())
            if code and code not in codes:
                codes.append(code)
        profile.languages = codes
        profile.save(update_fields=["languages"])


def skills_and_languages_backward(apps, schema_editor):
    TalentProfile = apps.get_model("profiles", "TalentProfile")
    for profile in TalentProfile.objects.all():
        profile.legacy_skills = list(profile.skills.values_list("name", flat=True))
        profile.languages = [LANGUAGES.get(code, code) for code in profile.languages or []]
        profile.save(update_fields=["legacy_skills", "languages"])


class Migration(migrations.Migration):
    dependencies = [
        ("profiles", "0001_initial"),
    ]

    operations = [
        # Talent
        migrations.RenameField("talentprofile", "full_name", "display_name"),
        migrations.AlterField(
            model_name="talentprofile",
            name="display_name",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="talentprofile",
            name="talent_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("artist", "Artist / muralist"),
                    ("photo_video", "Photographer / videographer"),
                    ("content_creator", "Content creator / social media"),
                    ("musician", "Musician / performer"),
                    ("wellness", "Yoga / wellness"),
                    ("culinary", "Chef / barista"),
                    ("hospitality", "Hospitality / front desk"),
                    ("teacher", "Teacher / workshop host"),
                    ("tech", "Tech / design"),
                    ("outdoor", "Outdoor / trek guide"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="talentprofile",
            name="emergency_contact_name",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="talentprofile",
            name="emergency_contact_phone",
            field=models.CharField(
                blank=True,
                help_text="E.164",
                max_length=16,
                validators=[apps.profiles.models.validate_phone],
            ),
        ),
        migrations.AddField(
            model_name="talentprofile",
            name="date_of_birth",
            field=models.DateField(
                blank=True, null=True, validators=[apps.profiles.models.validate_adult]
            ),
        ),
        migrations.AlterField(
            model_name="talentprofile",
            name="languages",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='ISO 639 codes, e.g. ["en", "hi"]',
                validators=[apps.profiles.models.validate_languages],
            ),
        ),
        migrations.AlterField(
            model_name="talentprofile",
            name="instagram_handle",
            field=models.CharField(
                blank=True,
                max_length=30,
                validators=[apps.profiles.models.INSTAGRAM_VALIDATOR],
            ),
        ),
        # Skills: JSON list -> Skill table
        migrations.CreateModel(
            name="Skill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=60)),
                ("slug", models.SlugField(max_length=60, unique=True)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["name"],
                "constraints": [
                    models.UniqueConstraint(
                        django.db.models.functions.text.Lower("name"),
                        name="profiles_skill_name_ci_unique",
                    )
                ],
            },
        ),
        migrations.RenameField("talentprofile", "skills", "legacy_skills"),
        migrations.AddField(
            model_name="talentprofile",
            name="skills",
            field=models.ManyToManyField(
                blank=True, related_name="talent_profiles", to="profiles.skill"
            ),
        ),
        migrations.RunPython(skills_and_languages_forward, skills_and_languages_backward),
        migrations.RemoveField("talentprofile", "legacy_skills"),
        # Vendor
        migrations.RenameField("vendorprofile", "property_type", "business_type"),
        migrations.AlterField(
            model_name="vendorprofile",
            name="business_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("hostel", "Hostel"),
                    ("homestay", "Homestay"),
                    ("guesthouse", "Guesthouse"),
                    ("hotel", "Hotel"),
                    ("resort", "Resort"),
                    ("cafe", "Café"),
                    ("restaurant", "Restaurant"),
                    ("camp", "Camp"),
                    ("farm", "Farm stay"),
                    ("tour_operator", "Tour operator"),
                    ("coworking", "Co-working / co-living"),
                    ("other", "Other"),
                ],
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="vendorprofile",
            name="business_name",
            field=models.CharField(blank=True, max_length=150),
        ),
        migrations.AlterField(
            model_name="vendorprofile",
            name="city",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AlterField(
            model_name="vendorprofile",
            name="state",
            field=models.CharField(
                blank=True,
                choices=apps.profiles.models.STATE_CHOICES,
                max_length=80,
            ),
        ),
        migrations.AlterField(
            model_name="vendorprofile",
            name="address",
            field=models.TextField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="vendorprofile",
            name="contact_name",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="vendorprofile",
            name="about",
            field=models.TextField(blank=True, max_length=3000),
        ),
    ]
