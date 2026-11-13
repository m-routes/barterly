"""The 0002 data step: JSON skills -> Skill rows, language names -> codes, and back."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = [("profiles", "0001_initial"), ("accounts", "0002_role_chosen_after_sign_up")]
AFTER = [("profiles", "0002_reshape_profiles")]


def migrate(targets):
    executor = MigrationExecutor(connection)
    executor.loader.build_graph()
    executor.migrate(targets)
    return executor.loader.project_state(targets).apps


def test_skills_and_languages_move_forward_and_back():
    old_apps = migrate(BEFORE)
    User = old_apps.get_model("accounts", "User")
    TalentProfile = old_apps.get_model("profiles", "TalentProfile")
    user = User.objects.create(phone="+919800011111", role="talent", password="!")
    TalentProfile.objects.create(
        user=user,
        full_name="Asha",
        skills=["Photography", "Mural art", "  "],
        languages=["English", "hindi", "hi", "Klingon"],
    )

    new_apps = migrate(AFTER)
    profile = new_apps.get_model("profiles", "TalentProfile").objects.get(user_id=user.pk)
    assert profile.display_name == "Asha"
    assert sorted(profile.skills.values_list("slug", flat=True)) == ["mural-art", "photography"]
    assert profile.languages == ["en", "hi"]

    old_apps = migrate(BEFORE)
    profile = old_apps.get_model("profiles", "TalentProfile").objects.get(user_id=user.pk)
    assert profile.full_name == "Asha"
    assert sorted(profile.skills) == ["Mural art", "Photography"]
    assert profile.languages == ["English", "Hindi"]

    migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
